param(
  [int]$Start = 1,
  [int]$End = 300,
  [int]$PollSeconds = 60,
  [string]$Owner = 'giovannifidel-collab',
  [string]$OutFile = 'razzo/super_factory/shard-readiness.json'
)
$ErrorActionPreference = 'Continue'

function GhJson([string[]]$Args) {
  $raw = & gh @Args 2>$null
  if ($LASTEXITCODE -ne 0) { return $null }
  if (-not $raw) { return $null }
  try { return ($raw -join "`n") | ConvertFrom-Json } catch { return $null }
}

function Snapshot {
  $rows = @()
  for ($i=$Start; $i -le $End; $i++) {
    $name = 'razzo-shard-{0:D4}' -f $i
    $repo = "$Owner/$name"
    $state = 'MISSING'; $activationSha = $null; $runId = $null; $conclusion = $null; $artifact = $null

    $repoInfo = GhJson @('api',"repos/$repo")
    if ($repoInfo) {
      $state = 'PENDING'
      $commits = GhJson @('api',"repos/$repo/commits?path=.razzo/shard.json&per_page=1")
      if ($commits -and $commits.Count -gt 0) {
        $activationSha = $commits[0].sha
        $runs = GhJson @('api',"repos/$repo/actions/workflows/razzo-shard-worker.yml/runs?event=push&per_page=20")
        if ($runs -and $runs.workflow_runs) {
          $run = $runs.workflow_runs | Where-Object { $_.head_sha -eq $activationSha } | Select-Object -First 1
          if ($run) {
            $runId = $run.id; $conclusion = $run.conclusion
            if ($run.status -eq 'completed' -and $run.conclusion -eq 'success') {
              $arts = GhJson @('api',"repos/$repo/actions/runs/$runId/artifacts?per_page=100")
              $expected = "razzo-self-health-$activationSha"
              if ($arts -and $arts.artifacts) {
                $a = $arts.artifacts | Where-Object { $_.name -eq $expected -and -not $_.expired } | Select-Object -First 1
                if ($a) { $artifact = $a.id; $state = 'READY' } else { $state = 'HEALTHY_NO_RECEIPT' }
              } else { $state = 'HEALTHY_NO_RECEIPT' }
            } elseif ($run.status -eq 'completed') { $state = 'FAILED' }
            else { $state = 'RUNNING' }
          }
        }
      }
    }
    $rows += [pscustomobject]@{ shard=$name; repository=$repo; state=$state; activation_sha=$activationSha; run_id=$runId; conclusion=$conclusion; artifact_id=$artifact }
  }

  $summary = [ordered]@{
    schema='razzo.shard-readiness.v1'; generated_at=(Get-Date).ToUniversalTime().ToString('o'); start=$Start; end=$End;
    ready=@($rows | Where-Object state -eq 'READY').Count;
    running=@($rows | Where-Object state -eq 'RUNNING').Count;
    pending=@($rows | Where-Object state -eq 'PENDING').Count;
    failed=@($rows | Where-Object state -eq 'FAILED').Count;
    healthy_no_receipt=@($rows | Where-Object state -eq 'HEALTHY_NO_RECEIPT').Count;
    missing=@($rows | Where-Object state -eq 'MISSING').Count;
    shards=$rows
  }
  $dir = Split-Path $OutFile -Parent; if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
  $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $OutFile
  Write-Host ("READY={0}/{1} RUNNING={2} PENDING={3} FAILED={4} NO_RECEIPT={5} MISSING={6}" -f $summary.ready,($End-$Start+1),$summary.running,$summary.pending,$summary.failed,$summary.healthy_no_receipt,$summary.missing)
  return $summary
}

while ($true) {
  $s = Snapshot
  if ($s.ready -eq ($End-$Start+1)) { Write-Host 'RAZZO SHARD FABRIC READY'; exit 0 }
  Start-Sleep -Seconds $PollSeconds
}
