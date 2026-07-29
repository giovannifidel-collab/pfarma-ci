param(
  [int]$Start = 1,
  [int]$End = 300,
  [int]$PollSeconds = 120,
  [string]$Owner = 'giovannifidel-collab',
  [string]$OutFile = 'razzo/super_factory/shard-readiness.json'
)
$ErrorActionPreference = 'Continue'

function Get-GhApiJson([string]$Endpoint) {
  $raw = & gh api $Endpoint 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
  try { return (($raw -join "`n") | ConvertFrom-Json) } catch { return $null }
}

function Get-ShardState([int]$Index) {
  $name = 'razzo-shard-{0:D4}' -f $Index
  $repo = "$Owner/$name"
  $row = [ordered]@{ shard=$name; repository=$repo; state='MISSING'; activation_sha=$null; run_id=$null; conclusion=$null; artifact_id=$null }

  $repoInfo = Get-GhApiJson "repos/$repo"
  if (-not $repoInfo) { return [pscustomobject]$row }
  $row.state = 'PENDING'

  $commits = Get-GhApiJson "repos/$repo/commits?path=.razzo/shard.json&per_page=1"
  if (-not $commits -or @($commits).Count -eq 0) { return [pscustomobject]$row }
  $activationSha = @($commits)[0].sha
  $row.activation_sha = $activationSha

  $runs = Get-GhApiJson "repos/$repo/actions/workflows/razzo-shard-worker.yml/runs?event=push&per_page=20"
  if (-not $runs -or -not $runs.workflow_runs) { return [pscustomobject]$row }
  $run = @($runs.workflow_runs) | Where-Object { $_.head_sha -eq $activationSha } | Select-Object -First 1
  if (-not $run) { return [pscustomobject]$row }

  $row.run_id = $run.id
  $row.conclusion = $run.conclusion
  if ($run.status -ne 'completed') { $row.state='RUNNING'; return [pscustomobject]$row }
  if ($run.conclusion -ne 'success') { $row.state='FAILED'; return [pscustomobject]$row }

  $arts = Get-GhApiJson "repos/$repo/actions/runs/$($run.id)/artifacts?per_page=100"
  $expected = "razzo-self-health-$activationSha"
  if ($arts -and $arts.artifacts) {
    $a = @($arts.artifacts) | Where-Object { $_.name -eq $expected -and -not $_.expired } | Select-Object -First 1
    if ($a) { $row.artifact_id=$a.id; $row.state='READY'; return [pscustomobject]$row }
  }
  $row.state='HEALTHY_NO_RECEIPT'
  return [pscustomobject]$row
}

while ($true) {
  $rows = for ($i=$Start; $i -le $End; $i++) { Get-ShardState $i }
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
  $dir=Split-Path $OutFile -Parent; if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
  $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $OutFile
  Write-Host ("READY={0}/{1} RUNNING={2} PENDING={3} FAILED={4} NO_RECEIPT={5} MISSING={6}" -f $summary.ready,($End-$Start+1),$summary.running,$summary.pending,$summary.failed,$summary.healthy_no_receipt,$summary.missing)
  if ($summary.ready -eq ($End-$Start+1)) { Write-Host 'RAZZO SHARD FABRIC READY'; exit 0 }
  Start-Sleep -Seconds $PollSeconds
}
