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
function Put-File([string]$Repo,[string]$Path,[string]$Message,[string]$LocalPath) {
  $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($LocalPath))
  $existing=$null
  try { $existing=Invoke-Gh @('api',"repos/$Repo/contents/$Path",'--jq','.sha') } catch { $existing=$null }
  $args=@('api','--method','PUT',"repos/$Repo/contents/$Path",'-f',"message=$Message",'-f',"content=$encoded")
  if ($existing) { $args += @('-f',"sha=$existing") }
  Invoke-Gh $args | Out-Null
}
$backoff = 60
$doneInBatch = 0
for ($i=$Start; $i -le $End; $i++) {
  $name = 'razzo-shard-{0:D4}' -f $i
  $repo = "$Owner/$name"
  try { Invoke-Gh @('repo','view',$repo,'--json','nameWithOwner') | Out-Null }
  catch { Write-Host "SKIP missing $repo"; continue }
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
      # Install/update the workflow first. The subsequent manifest write is the
      # activation edge: push:path=.razzo/shard.json starts exact-SHA self-health.
      Put-File $repo '.github/workflows/razzo-shard-worker.yml' "RAZZO provision $name worker" $workflowPath
      Start-Sleep -Seconds $DelaySeconds
      Put-File $repo '.razzo/shard.json' "RAZZO activate $name self-health" $manifestPath
      Write-Host "PROVISIONED+ACTIVATED $repo"
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
Write-Host 'RAZZO shard provisioning + self-activation pass complete.'
