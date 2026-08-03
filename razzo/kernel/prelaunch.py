from __future__ import annotations

import hashlib, json, os, re, tempfile, time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath, Path
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

def normalize_repo_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip() or "\\" in raw or raw.startswith("/") or "\x00" in raw:
        raise ValueError("repository path must be relative POSIX text")
    path = PurePosixPath(raw)
    if not path.parts or any(part in {"", ".", ".."} or part.startswith("~") for part in path.parts):
        raise ValueError("repository path contains unsafe segments")
    return path.as_posix()

def surface_contains(surface: str, path: str) -> bool:
    s, p = normalize_repo_path(surface), normalize_repo_path(path)
    if s.endswith("/**"):
        prefix = s[:-3].rstrip("/")
        return p == prefix or p.startswith(prefix + "/")
    if s.endswith("/*"):
        prefix = s[:-2].rstrip("/")
        return p.startswith(prefix + "/") and "/" not in p[len(prefix)+1:]
    return p == s or p.startswith(s.rstrip("/") + "/")

class ProviderState(str, Enum):
    VERIFIED_INTERACTIVE = "VERIFIED_INTERACTIVE"
    VERIFIED_UNATTENDED = "VERIFIED_UNATTENDED"
    PENDING = "PENDING"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class ProviderContract:
    provider_id: str
    state: ProviderState
    can_reason: bool
    can_write_code: bool
    can_open_pr: bool
    unattended_trigger: bool
    additional_cost_required: bool
    evidence: tuple[str, ...] = ()
    def validate(self) -> None:
        if not _SAFE_ID_RE.fullmatch(self.provider_id): raise ValueError("invalid provider id")
        if self.state in {ProviderState.VERIFIED_INTERACTIVE, ProviderState.VERIFIED_UNATTENDED}:
            if not (self.can_reason and self.can_write_code and self.can_open_pr): raise ValueError("verified provider lacks capabilities")
            if not self.evidence: raise ValueError("verified provider requires evidence")
        if self.state == ProviderState.VERIFIED_UNATTENDED and not self.unattended_trigger:
            raise ValueError("unattended provider requires unattended trigger")
    @property
    def pilot_eligible(self) -> bool:
        self.validate(); return self.state in {ProviderState.VERIFIED_INTERACTIVE, ProviderState.VERIFIED_UNATTENDED}
    @property
    def continuous_eligible(self) -> bool:
        self.validate(); return self.state == ProviderState.VERIFIED_UNATTENDED

@dataclass(frozen=True)
class RepositoryContract:
    project_id: str
    repository: str
    canonical_lane: str
    exact_base_sha: str
    allowed_surfaces: tuple[str, ...]
    forbidden_surfaces: tuple[str, ...]
    focused_test_commands: tuple[str, ...]
    product_ci_check: str
    robot_qa_check: str
    rollback_strategy: str
    max_parallel: int = 3
    product_writes: bool = False
    auto_merge: bool = False
    def validate(self) -> None:
        if not _SAFE_ID_RE.fullmatch(self.project_id): raise ValueError("invalid project id")
        if "/" not in self.repository or not self.canonical_lane: raise ValueError("repository and lane required")
        if not _SHA_RE.fullmatch(self.exact_base_sha): raise ValueError("exact base SHA required")
        if not 1 <= self.max_parallel <= 5: raise ValueError("max_parallel outside kernel cap")
        allowed = tuple(normalize_repo_path(x) for x in self.allowed_surfaces)
        forbidden = tuple(normalize_repo_path(x) for x in self.forbidden_surfaces)
        if not allowed or not forbidden: raise ValueError("allowed/forbidden surfaces required")
        for a in allowed:
            for f in forbidden:
                if surface_contains(a, f) or surface_contains(f, a): raise ValueError(f"surface overlap: {a} vs {f}")
        if not self.focused_test_commands or any(not c.strip() for c in self.focused_test_commands): raise ValueError("focused tests required")
        if not self.product_ci_check or not self.robot_qa_check or self.product_ci_check == self.robot_qa_check: raise ValueError("independent CI and Robot QA required")
        if not self.rollback_strategy.strip(): raise ValueError("rollback required")
        if self.auto_merge or self.product_writes: raise ValueError("prelaunch forbids auto merge and product writes")

@dataclass(frozen=True)
class PatchBundle:
    bundle_id: str; objective_id: str; base_sha: str; candidate_sha: str
    changed_files: tuple[str, ...]; deleted_files: tuple[str, ...]; diff_bytes: int
    test_commands: tuple[str, ...]; assertions: tuple[str, ...]; content_digest: str
    def validate(self, contract: RepositoryContract, max_diff_bytes: int = 500_000) -> None:
        contract.validate()
        if not _SAFE_ID_RE.fullmatch(self.bundle_id) or not _SHA256_RE.fullmatch(self.objective_id): raise ValueError("invalid bundle identity")
        if not _SHA_RE.fullmatch(self.base_sha) or not _SHA_RE.fullmatch(self.candidate_sha) or self.base_sha == self.candidate_sha: raise ValueError("real exact-SHA diff required")
        if not 0 < self.diff_bytes <= max_diff_bytes: raise ValueError("diff size outside policy")
        paths = tuple(normalize_repo_path(p) for p in self.changed_files + self.deleted_files)
        if not paths or len(set(paths)) != len(paths): raise ValueError("missing or duplicate paths")
        for path in paths:
            if not any(surface_contains(s, path) for s in contract.allowed_surfaces): raise ValueError(f"outside allowed surfaces: {path}")
            if any(surface_contains(s, path) for s in contract.forbidden_surfaces): raise ValueError(f"forbidden path: {path}")
        if self.test_commands != contract.focused_test_commands: raise ValueError("test command mismatch")
        if not self.assertions or not _SHA256_RE.fullmatch(self.content_digest): raise ValueError("assertions and content digest required")

@dataclass(frozen=True)
class ExactHeadReceipt:
    objective_id: str; bundle_id: str; candidate_sha: str; branch_head_sha: str
    product_ci_sha: str; robot_qa_sha: str; product_ci_check: str; robot_qa_check: str
    changed_files: tuple[str, ...]; assertions: tuple[str, ...]
    def validate(self, contract: RepositoryContract) -> None:
        contract.validate()
        shas = (self.candidate_sha, self.branch_head_sha, self.product_ci_sha, self.robot_qa_sha)
        if any(not _SHA_RE.fullmatch(s) for s in shas) or len(set(shas)) != 1: raise ValueError("all gates must use one exact SHA")
        if self.product_ci_check != contract.product_ci_check or self.robot_qa_check != contract.robot_qa_check: raise ValueError("authoritative check mismatch")
        if not self.changed_files or not self.assertions: raise ValueError("real diff and assertions required")

@dataclass(frozen=True)
class WorkUnitReceipt:
    unit_id: str; collision_domain: str; bundle: PatchBundle; exact_head: ExactHeadReceipt
    def validate(self, contract: RepositoryContract) -> None:
        if not _SAFE_ID_RE.fullmatch(self.unit_id) or not _SAFE_ID_RE.fullmatch(self.collision_domain): raise ValueError("invalid unit identity")
        self.bundle.validate(contract); self.exact_head.validate(contract)
        if (self.bundle.bundle_id, self.bundle.objective_id, self.bundle.candidate_sha) != (self.exact_head.bundle_id, self.exact_head.objective_id, self.exact_head.candidate_sha): raise ValueError("bundle/receipt mismatch")

@dataclass(frozen=True)
class AggregateReceipt:
    wave_id: str; objective_id: str; units: tuple[WorkUnitReceipt, ...]
    concurrent_peak: int; retries: int; duplicates_ignored: int
    def validate(self, contract: RepositoryContract) -> None:
        if not _SHA256_RE.fullmatch(self.wave_id) or not _SHA256_RE.fullmatch(self.objective_id): raise ValueError("invalid aggregate identity")
        if len(self.units) < 2 or not 2 <= self.concurrent_peak <= contract.max_parallel: raise ValueError("multi-workstream concurrency proof missing")
        ids, domains = set(), set()
        for unit in self.units:
            unit.validate(contract)
            if unit.unit_id in ids: raise ValueError("duplicate execution unit")
            if unit.collision_domain in domains: raise ValueError("parallel collision reuse")
            ids.add(unit.unit_id); domains.add(unit.collision_domain)
            if unit.bundle.objective_id != self.objective_id: raise ValueError("aggregate objective mismatch")
        if self.retries < 0 or self.duplicates_ignored < 0: raise ValueError("negative telemetry")

class JournalConflict(RuntimeError): pass
@dataclass
class JournalSnapshot:
    generation: int; objective_id: str; state: str; events: list[dict[str, Any]] = field(default_factory=list)
    def to_dict(self): return {"generation":self.generation,"objective_id":self.objective_id,"state":self.state,"events":self.events}
    @classmethod
    def from_dict(cls, v: Mapping[str, Any]): return cls(int(v["generation"]), str(v["objective_id"]), str(v["state"]), list(v.get("events", [])))

class AtomicJournalStore:
    def __init__(self, path: str | Path): self.path = Path(path)
    def load(self):
        if not self.path.exists(): return None
        return JournalSnapshot.from_dict(json.loads(self.path.read_text()))
    def compare_and_swap(self, expected_generation: int, snapshot: JournalSnapshot):
        current = self.load(); observed = -1 if current is None else current.generation
        if observed != expected_generation or snapshot.generation != expected_generation + 1: raise JournalConflict("journal generation conflict")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name+".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w") as h: json.dump(snapshot.to_dict(), h, sort_keys=True); h.flush(); os.fsync(h.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

class FileLease:
    def __init__(self, directory: str | Path, key: str, owner: str, ttl_seconds: int = 60):
        if not _SAFE_ID_RE.fullmatch(key) or not _SAFE_ID_RE.fullmatch(owner): raise ValueError("invalid lease identity")
        self.directory=Path(directory); self.key=key; self.owner=owner; self.ttl_seconds=ttl_seconds
        self.path=self.directory/(hashlib.sha256(key.encode()).hexdigest()+".lease")
    def acquire(self, now: float | None = None):
        now = time.time() if now is None else now; self.directory.mkdir(parents=True, exist_ok=True)
        payload={"key":self.key,"owner":self.owner,"expires_at":now+self.ttl_seconds}
        try: fd=os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        except FileExistsError:
            existing=json.loads(self.path.read_text())
            if float(existing["expires_at"]) > now: raise JournalConflict("lease already held")
            try: self.path.unlink()
            except FileNotFoundError: pass
            return self.acquire(now)
        with os.fdopen(fd, "w") as h: json.dump(payload, h, sort_keys=True); h.flush(); os.fsync(h.fileno())
    def release(self):
        if not self.path.exists(): return
        if json.loads(self.path.read_text()).get("owner") != self.owner: raise JournalConflict("lease owner mismatch")
        self.path.unlink()

@dataclass(frozen=True)
class RollbackPlan:
    objective_id: str; candidate_branch: str; expected_head_sha: str
    delete_candidate_branch: bool; close_draft_pr: bool; release_leases: tuple[str, ...]
    restore_journal_generation: int; product_rollback_required: bool = False
    def validate(self):
        if not _SHA256_RE.fullmatch(self.objective_id) or not self.candidate_branch.startswith("razzo/o/") or not _SHA_RE.fullmatch(self.expected_head_sha): raise ValueError("invalid rollback identity")
        if not self.delete_candidate_branch or not self.close_draft_pr or not self.release_leases: raise ValueError("rollback cleanup incomplete")
        if self.restore_journal_generation < 0 or self.product_rollback_required: raise ValueError("unsafe rollback plan")

@dataclass(frozen=True)
class GateResult:
    ready: bool; missing: tuple[str, ...]; warnings: tuple[str, ...]

@dataclass(frozen=True)
class ActivationEvidence:
    provider: ProviderContract; repository_contract: RepositoryContract; aggregate_receipt: AggregateReceipt | None
    persistent_recovery_passed: bool; concurrency_passed: bool; patch_security_passed: bool
    rollback_passed: bool; legacy_lane_reconciled: bool; shadow_mutations: int; all_ci_green: bool
    human_approval: bool = False
    def evaluate(self, continuous: bool) -> GateResult:
        missing=[]; warnings=[]
        try: self.provider.validate()
        except Exception as exc: missing.append(f"provider invalid: {exc}")
        if continuous and not self.provider.continuous_eligible: missing.append("verified unattended execution provider")
        if not continuous and not self.provider.pilot_eligible: missing.append("verified interactive execution provider")
        try: self.repository_contract.validate()
        except Exception as exc: missing.append(f"repository contract invalid: {exc}")
        if self.aggregate_receipt is None: missing.append("real multi-workstream aggregate receipt")
        else:
            try: self.aggregate_receipt.validate(self.repository_contract)
            except Exception as exc: missing.append(f"aggregate receipt invalid: {exc}")
        checks=((self.persistent_recovery_passed,"persistent recovery"),(self.concurrency_passed,"real concurrency"),(self.patch_security_passed,"patch security"),(self.rollback_passed,"rollback proof"),(self.legacy_lane_reconciled,"legacy lane reconciliation"),(self.shadow_mutations==0,"zero-mutation shadow"),(self.all_ci_green,"all authoritative CI green"))
        missing.extend(label for ok,label in checks if not ok)
        if not self.human_approval: warnings.append("human activation approval not granted")
        return GateResult(not missing, tuple(missing), tuple(warnings))
