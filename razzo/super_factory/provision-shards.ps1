param(
  [int]$Start = 1,
  [int]$End = 300,
  [int]$BatchSize = 5,
  [int]$DelaySeconds = 2,
  [string]$Owner = 'giovannifidel-collab',
  [string]$ControlPlane = 'giovannifidel-collab/pfarma-ci'
)
$ErrorActionPreference = 'Stop'
$template = Join-Path $PSScriptRoot 'shard-worker-template.yml'
if (!(Test-Path $template)) { throw "Missing worker template: $template" }
$worker = Get-Content $template -Raw
function Invoke-Gh([string[]]$Args) {
  $out = & gh @Args 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($out -join "`n") }
  return ($out -join "`n")
}
function Is-SecondaryLimit([string]$Message) {
  return $Message -match 'secondary rate limit|temporarily blocked from content creation|HTTP 403'
}
$backoff = 60
$doneInBatch = 0
for ($i=$Start; $i -le $End; $i++) {
  $name = 'razzo-shard-{0:D4}' -f $i
  $repo = "$Owner/$name"
  try {
    Invoke-Gh @('repo','view',$repo,'--json','nameWithOwner') | Out-Null
  } catch {
    Write-Host "SKIP missing $repo"
    continue
  }
  $manifest = @{
    schema='razzo.shard.v1'; shard_id=('shard-{0:D4}' -f $i); repository=$repo;
    control_plane=$ControlPlane; state='PROVISIONED'; exact_sha_required=$true;
    collision_domain_lease_required=$true; idempotency_required=$true; product_progress=$false
  } | ConvertTo-Json -Depth 5
  $tmp = Join-Path $env:TEMP "$name-razzo"
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $manifestPath = Join-Path $tmp 'shard.json'; $workflowPath = Join-Path $tmp 'worker.yml'
  Set-Content -Path $manifestPath -Value $manifest -Encoding utf8
  Set-Content -Path $workflowPath -Value $worker -Encoding utf8
  $attempt = 0
  while ($true) {
    try {
      $attempt++
      Invoke-Gh @('api','--method','PUT',"repos/$repo/contents/.razzo/shard.json",'-f',"message=RAZZO provision $name manifest",'-f',"content=$([Convert]::ToBase64String([IO.File]::ReadAllBytes($manifestPath)))") | Out-Null
      Start-Sleep -Seconds $DelaySeconds
      Invoke-Gh @('api','--method','PUT',"repos/$repo/contents/.github/workflows/razzo-shard-worker.yml",'-f',"message=RAZZO provision $name worker",'-f',"content=$([Convert]::ToBase64String([IO.File]::ReadAllBytes($workflowPath)))") | Out-Null
      Write-Host "PROVISIONED $repo"
      $backoff = 60
      break
    } catch {
      $msg = $_.Exception.Message
      if (!(Is-SecondaryLimit $msg)) { Write-Warning "FAILED $repo :: $msg"; break }
      Write-Warning "SECONDARY LIMIT $repo; sleeping $backoff seconds and retrying same shard"
      Start-Sleep -Seconds $backoff
      $backoff = [Math]::Min($backoff * 2, 3600)
    }
  }
  $doneInBatch++
  Start-Sleep -Seconds $DelaySeconds
  if ($doneInBatch -ge $BatchSize) {
    Write-Host "BATCH COMPLETE ($BatchSize). Pause 30 seconds before next batch."
    Start-Sleep -Seconds 30
    $doneInBatch = 0
  }
}
Write-Host 'RAZZO shard provisioning pass complete.'
