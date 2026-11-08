"""S9.2 one-shot OWNER-approved Pages preview diagnostic; never production deploy.

Requires pfarma-ci-trusted secret-scoped runner. Config mutations are TEMPORARY,
reverted in finally. No credentials are printed, no project code is changed.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT = "hive-alveare"
PRIVATE_REPO = "giovannifidel-collab/hive-alveare"
PRIVATE_MAIN = "296677c77946b91ca1c8f9da70d41d87b975c5e4"
PREVIEW_BRANCH = "convergence/s9-pages-legacy-build-compat-20261108"
PREVIEW_SHA = "8920b575defba8d806d8638de66794078d5c5403"
ROLLBACK_SHA = "a0ba9b06593f514182ae9fcabdec073c30755066"
COMMAND = "node ../ops/queen/s9/pages-legacy-import-adapter.mjs --apply-ephemeral"
BASE = "https://api.cloudflare.com/client/v4"


class Abort(Exception):
    pass


def request(token, path, method="GET", data=None):
    payload = None
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/json"}
    if isinstance(data, dict):
        payload = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, headers=headers,
                                 data=payload, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            error = json.load(exc)
        except Exception:
            error = {}
        return exc.code, error
    except Exception:
        return 0, {}


def trusted_result(status, response):
    return status in (200, 201, 202) and response.get("success") is True


def get_project(token, account_id):
    s, r = request(token, "/accounts/" + account_id +
                   "/pages/projects/" + PROJECT)
    if not trusted_result(s, r) or not isinstance(r.get("result"), dict):
        raise Abort("PAGES_GET_PROJECT_UNAVAILABLE")
    return r["result"]


def find_account(token):
    s, r = request(token, "/accounts?per_page=50")
    if not trusted_result(s, r):
        return None
    matched = []
    for a in r.get("result", []):
        account_id = a.get("id")
        if not isinstance(account_id, str) or not re.fullmatch(r"[0-9a-f]{32}", account_id):
            continue
        status, p = request(token, "/accounts/" + account_id + "/pages/projects/" + PROJECT)
        if trusted_result(status, p) and (p.get("result") or {}).get("name") == PROJECT:
            matched.append(account_id)
    return matched[0] if len(matched) == 1 else None


def ensure_identity(p, original=None):
    b = p.get("build_config") or {}
    c = (p.get("source") or {}).get("config") or {}
    if (p.get("name") != PROJECT or
        (p.get("source") or {}).get("type") != "github" or
        c.get("repo_name") != "hive-alveare" or
        c.get("production_branch") != "main" or
        b.get("root_dir") != "cloudflare" or
        b.get("destination_dir") != "public"):
        raise Abort("PAGES_IDENTITY_OR_BUILD_ROOT_CHANGED")
    if original and (b.get("root_dir") != original["root_dir"] or
                     b.get("destination_dir") != original["destination_dir"]):
        raise Abort("PAGES_OTHER_BUILD_FIELDS_DRIFTED")
    return b, c


def pages_deployments(token, account_id, count=8):
    result = []
    for page in range(1, count + 1):
        s, r = request(token, "/accounts/" + account_id +
                       "/pages/projects/" + PROJECT +
                       "/deployments?per_page=20&page=" + str(page))
        if not trusted_result(s, r) or not isinstance(r.get("result"), list):
            raise Abort("PAGES_DEPLOYMENT_HISTORY_UNAVAILABLE")
        batch = r["result"]
        result.extend(batch)
        if len(batch) < 20:
            break
    return result


def source_sha(d):
    return ((d.get("deployment_trigger") or {}).get("metadata") or {}).get("commit_hash")


def source_branch(d):
    return ((d.get("deployment_trigger") or {}).get("metadata") or {}).get("branch")


def find_rollback_and_preview(token, account_id):
    deployments = pages_deployments(token, account_id)
    rollback = [d for d in deployments if
                d.get("environment") == "production" and
                (d.get("latest_stage") or {}).get("status") == "success" and
                source_sha(d) == ROLLBACK_SHA]
    preview = [d for d in deployments if
               d.get("environment") == "preview" and
               (d.get("latest_stage") or {}).get("status") == "failure" and
               source_sha(d) == PREVIEW_SHA and
               source_branch(d) == PREVIEW_BRANCH]
    if len(rollback) < 1:
        raise Abort("PAGES_CERTIFIED_PRODUCTION_ROLLBACK_TARGET_MISSING")
    if not preview:
        raise Abort("PAGES_EXACT_PREVIEW_SHA_FAILURE_NOT_FOUND")
    print("S9_PAGES_ROLLBACK=HISTORIC_SUCCESS_VERIFIED")
    print("S9_PAGES_PREVIEW_SOURCE=EXACT_SHA_AND_BRANCH_MATCH")
    return preview[0]


def patch(token, account_id, body):
    s, r = request(token, "/accounts/" + account_id + "/pages/projects/" + PROJECT,
                   method="PATCH", data=body)
    if not trusted_result(s, r):
        raise Abort("PAGES_PATCH_DENIED_HTTP_" + str(s))
    return r.get("result") or {}


def patch_prod(token, account, enabled):
    return patch(token, account, {
        "source": {"type": "github",
                   "config": {"production_deployments_enabled": enabled}}})


def patch_build(token, account, command):
    return patch(token, account, {"build_config": {"build_command": command}})


def restore(token, account, initial, changed_prod, changed_build):
    """Restore original build command FIRST, then production auto-deploy setting."""
    errors = []
    # Detect any applied change even if an API response was lost.
    current_build, current_config = ensure_identity(get_project(token, account), initial)
    if current_build.get("build_command") not in (initial["build_command"], COMMAND):
        raise Abort("UNRECOGNIZED_BUILD_COMMAND_MANUAL_HOLD")
    if current_config.get("production_deployments_enabled") not in (False, initial["production_enabled"]):
        raise Abort("UNRECOGNIZED_PRODUCTION_DEPLOY_SETTING_MANUAL_HOLD")
    changed_build = changed_build or current_build.get("build_command") == COMMAND
    changed_prod = changed_prod or current_config.get("production_deployments_enabled") is False
    if changed_build:
        try:
            patch_build(token, account, initial["build_command"])
            b, _ = ensure_identity(get_project(token, account), initial)
            if b.get("build_command") != initial["build_command"]:
                raise Abort("RESTORE_BUILD_COMMAND_READBACK_MISMATCH")
            print("S9_PAGES_ORIGINAL_BUILD_COMMAND_RESTORED=PASS")
        except Exception:
            errors.append("RESTORE_BUILD_COMMAND_FAILED")
    if changed_prod and not errors:
        try:
            patch_prod(token, account, initial["production_enabled"])
            _, c = ensure_identity(get_project(token, account), initial)
            if c.get("production_deployments_enabled") != initial["production_enabled"]:
                raise Abort("RESTORE_PRODUCTION_SETTING_READBACK_MISMATCH")
            print("S9_PAGES_ORIGINAL_PRODUCTION_AUTO_SETTING_RESTORED=PASS")
        except Exception:
            errors.append("RESTORE_PRODUCTION_SETTING_FAILED")
    if errors:
        raise Abort(",".join(errors) +
                    "_PRODUCTION_AUTO_DEPLOY_MUST_REMAIN_DISABLED_UNTIL_MANUALLY_RESTORED")
    b, c = ensure_identity(get_project(token, account), initial)
    if b.get("build_command") != initial["build_command"] or (
            c.get("production_deployments_enabled") != initial["production_enabled"]):
        raise Abort("FINAL_PAGES_CONFIG_RESTORE_NOT_ATTESTED")
    print("S9_PAGES_CONFIG_RESTORED_EXACT=PASS")


def retry_preview(token, account, preview):
    target = preview.get("id")
    if not isinstance(target, str) or not re.fullmatch(r"[0-9a-f-]{36}", target):
        raise Abort("PREVIEW_DEPLOYMENT_ID_INVALID")
    s, data = request(token, "/accounts/" + account +
                      "/pages/projects/" + PROJECT +
                      "/deployments/" + target + "/retry", "POST", {})
    if not trusted_result(s, data):
        raise Abort("PREVIEW_RETRY_HTTP_" + str(s))
    result = data.get("result") or {}
    preview_id = result.get("id")
    if not isinstance(preview_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", preview_id):
        raise Abort("PREVIEW_RETRY_DID_NOT_RETURN_DEPLOYMENT_ID")
    if result.get("environment") not in (None, "preview"):
        raise Abort("PREVIEW_RETRY_WRONG_ENVIRONMENT")
    print("S9_PAGES_PREVIEW_RETRY_ACCEPTED=TRUE")
    print("S9_PAGES_PREVIEW_DEPLOYMENT_ID=" + preview_id)
    return preview_id


def wait_preview(token, account, preview_id):
    path = "/accounts/" + account + "/pages/projects/" + PROJECT + "/deployments/" + preview_id
    for attempt in range(24):
        s, r = request(token, path)
        if not trusted_result(s, r):
            raise Abort("PREVIEW_DEPLOYMENT_GET_UNAVAILABLE")
        p = r.get("result") or {}
        if (p.get("id") != preview_id or
            p.get("environment") != "preview" or
            source_sha(p) != PREVIEW_SHA or
            source_branch(p) != PREVIEW_BRANCH):
            raise Abort("PREVIEW_DEPLOYMENT_PROVENANCE_INVALID")
        stage = (p.get("latest_stage") or {}).get("status")
        if stage == "success":
            print("S9_PAGES_PREVIEW_DEPLOY=SUCCESS")
            return p
        if stage in ("failure", "cancelled"):
            raise Abort("PREVIEW_DEPLOYMENT_" + stage.upper())
        if attempt % 4 == 0:
            print("S9_PAGES_PREVIEW_STAGE=" + str(stage)[:25])
        time.sleep(8)
    raise Abort("PREVIEW_DEPLOYMENT_TIMEOUT_NO_SUCCESS_ATTESTATION")


def protected_preview_contract(deploy):
    url = deploy.get("url")
    if not isinstance(url, str) or not url.startswith("https://") or        not url.endswith(".hive-alveare.pages.dev"):
        raise Abort("PREVIEW_URL_NOT_CANONICAL")
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID") or ""
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET") or ""
    if not client_id or not client_secret:
        raise Abort("CLOUDFLARE_ACCESS_HEADERS_UNAVAILABLE")
    base = url.rstrip("/")
    headers = {"CF-Access-Client-Id": client_id,
               "CF-Access-Client-Secret": client_secret,
               "Accept": "application/json"}
    for path, component in [
        ("/api/runtime-health", None),
        ("/api/queen-s8-portfolio", "queen-portfolio-awareness"),
        ("/api/queen-s7-e2e", None)
    ]:
        try:
            req = urllib.request.Request(base + path, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status != 200:
                    raise Abort("PREVIEW_GET_NON_200")
                data = json.load(resp)
        except Exception:
            raise Abort("PREVIEW_PROTECTED_ENDPOINT_UNAVAILABLE_" + path.split("/")[-1])
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise Abort("PREVIEW_ENDPOINT_CONTRACT_FAILED_" + path.split("/")[-1])
        if component and data.get("component") != component:
            raise Abort("PREVIEW_PORTFOLIO_CONTRACT_INVALID")
        if data.get("paid_fallback") is True or data.get("default_dispatch") not in (None, "DENY"):
            raise Abort("PREVIEW_POLICY_VIOLATION")
        print("S9_PREVIEW_PROTECTED_GET_" + path.split("/")[-1].upper().replace("-", "_") + "=PASS")
    print("S9_PREVIEW_CONTRACT_CERTIFIED=TRUE")


def main():
    if os.environ.get("S9_AUTHORIZED_SCOPE") != "BUILD_CONFIG_TEMPORARY_PREVIEW_ONLY_2026_11_08":
        raise Abort("OWNER_PREVIEW_SCOPE_NOT_VERIFIED")
    if os.environ.get("S9_EXACT_PRIVATE_MAIN") != PRIVATE_MAIN:
        raise Abort("PINNED_QUEEN_MAIN_MISMATCH")
    tokens = []
    for candidate in (os.environ.get("CF_TOKEN_PRIMARY"), os.environ.get("CF_TOKEN_SECONDARY")):
        if candidate and candidate not in tokens:
            tokens.append(candidate)
    if not tokens:
        raise Abort("NO_CLOUDFLARE_READER_OR_WRITER")
    candidates = [(token, find_account(token)) for token in tokens]
    candidates = [(token, account) for token, account in candidates if account]
    if not candidates:
        raise Abort("UNIQUE_CLOUDFLARE_PROJECT_NOT_READABLE")
    token, account = candidates[0]
    project = get_project(token, account)
    b, c = ensure_identity(project)
    if b.get("build_command") not in ("", None) or        c.get("production_deployments_enabled") is not True:
        raise Abort("PREVIOUS_BUILD_CONFIG_OR_PRODUCTION_SETTING_CHANGED")
    initial = {"build_command": b.get("build_command") or "",
               "root_dir": b["root_dir"],
               "destination_dir": b["destination_dir"],
               "production_enabled": c["production_deployments_enabled"]}
    preview = find_rollback_and_preview(token, account)
    print("S9_PAGES_PREVIEW_ONLY_OWNER_SCOPE=PASS")
    changed_prod = changed_build = False
    result_error = None
    try:
        try:
            patch_prod(token, account, False)
        except Abort as err:
            if "HTTP_403" not in str(err) or len(candidates) < 2:
                raise
            token, account = candidates[1]
            # Re-verify a distinct token's permissions & identical project.
            p = get_project(token, account)
            b2, c2 = ensure_identity(p)
            if b2.get("build_command") not in ("", None) or                c2.get("production_deployments_enabled") is not True:
                raise Abort("ALTERNATE_TOKEN_PROJECT_DRIFT")
            patch_prod(token, account, False)
        changed_prod = True
        p = get_project(token, account)
        b1, c1 = ensure_identity(p, initial)
        if c1.get("production_deployments_enabled") is not False:
            raise Abort("PRODUCTION_AUTO_DISABLE_NOT_VERIFIED")
        print("S9_PRODUCTION_AUTO_DEPLOY_TEMPORARILY_DISABLED=TRUE")
        patch_build(token, account, COMMAND)
        changed_build = True
        p = get_project(token, account)
        b2, c2 = ensure_identity(p, initial)
        if (b2.get("build_command") != COMMAND or
            c2.get("production_deployments_enabled") is not False):
            raise Abort("BUILD_CONFIG_READBACK_FAILED")
        print("S9_PAGES_BUILD_COMMAND_APPLIED_TO_PREVIEW_TEST=PASS")
        dep_id = retry_preview(token, account, preview)
        completed = wait_preview(token, account, dep_id)
        protected_preview_contract(completed)
    except Exception as exc:
        result_error = str(exc) if isinstance(exc, Abort) else "UNEXPECTED_PREVIEW_RUNTIME_ERROR"
        print("S9_PREVIEW_ABORT=" + re.sub(r"[^A-Za-z0-9_,-]", "_", result_error)[:190])
    finally:
        restore(token, account, initial, changed_prod, changed_build)
    if result_error:
        raise Abort(result_error)
    print("S9_2_PREVIEW_LIVE_WITH_FULL_ROLLBACK=PASS")
    print("S9_2_PRODUCTION_DEPLOYMENT=NOT_ATTEMPTED")


if __name__ == "__main__":
    try:
        main()
    except Abort as exc:
        print("S9_PAGES_SAFE_ABORT=" + re.sub(r"[^A-Za-z0-9_,-]", "_", str(exc))[:200])
        raise SystemExit(1)
