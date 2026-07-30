param(
  [Parameter(Mandatory=$true)][string]$Queue,
  [string]$Readiness='razzo/super_factory/shard-readiness.json',
  [string]$Leases='razzo/super_factory/shard-leases.json',
  [string]$Receipts='razzo/super_factory/dispatch-receipts',
  [string]$Compositions='razzo/super_factory/compositions',
  [int]$Limit=20
)
$ErrorActionPreference='Stop'
$mutex=[Threading.Mutex]::new($false,'RAZZO_HOMO_NOVUS_PHASE3')
if(-not $mutex.WaitOne(0)){throw 'Another HOMO NOVUS phase-3 runner owns the local lease.'}
try {
  powershell -ExecutionPolicy Bypass -File .\razzo\super_factory\dispatch-work.ps1 -Queue $Queue -Readiness $Readiness -Leases $Leases -Receipts $Receipts -Limit $Limit
  if($LASTEXITCODE -ne 0){throw 'Phase 2 dispatch failed closed.'}
  $queueData=Get-Content $Queue -Raw | ConvertFrom-Json
  $generations=@($queueData.items | ForEach-Object {$_.generation_id} | Sort-Object -Unique)
  if($generations.Count -ne 1){throw 'Phase 3 requires exactly one generation per queue.'}
  New-Item -ItemType Directory -Force $Compositions | Out-Null
  $out=Join-Path $Compositions ("$($generations[0]).json")
  python .\razzo\super_factory\phase3_composer.py --queue $Queue --leases $Leases --receipts $Receipts --out $out
  if($LASTEXITCODE -ne 0){throw 'Phase 3 composition failed closed.'}
  Write-Host "HOMO NOVUS PHASE 3 COMPLETE composition=$out"
}
finally {$mutex.ReleaseMutex();$mutex.Dispose()}
