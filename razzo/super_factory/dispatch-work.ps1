param(
  [Parameter(Mandatory=$true)][string]$Queue,
  [string]$Readiness = 'razzo/super_factory/shard-readiness.json',
  [string]$Leases = 'razzo/super_factory/shard-leases.json',
  [string]$Receipts = 'razzo/super_factory/dispatch-receipts',
  [int]$Limit = 20,
  [int]$LeaseMinutes = 30,
  [int]$PollSeconds = 10,
  [int]$TimeoutMinutes = 20
)
$ErrorActionPreference = 'Stop'
$mutex = [Threading.Mutex]::new($false, 'RAZZO_HOMO_NOVUS_DISPATCHER')
if (-not $mutex.WaitOne(0)) { throw 'Another HOMO NOVUS dispatcher owns the local mutation lease.' }
try {
  if (!(Test-Path $Readiness)) { throw "Missing readiness snapshot: $Readiness" }
  if (!(Test-Path $Queue)) { throw "Missing work queue: $Queue" }
  if (!(Test-Path $Leases)) {
    [IO.File]::WriteAllText((Resolve-Path .).Path + '\' + $Leases.Replace('/','\'), '{"schema":"razzo.shard-leases.v1","leases":[]}', [Text.UTF8Encoding]::new($false))
  }
  New-Item -ItemType Directory -Force $Receipts | Out-Null
  $planPath = Join-Path $env:TEMP 'homo-novus-dispatch-plan.json'
  python .\razzo\super_factory\dispatcher.py --readiness $Readiness --queue $Queue --leases $Leases --out $planPath --limit $Limit
  if ($LASTEXITCODE -ne 0) { throw 'Dispatcher planning failed closed.' }
  $plan = Get-Content $planPath -Raw | ConvertFrom-Json
  $leaseState = Get-Content $Leases -Raw | ConvertFrom-Json
  if (-not $leaseState.leases) { $leaseState | Add-Member -NotePropertyName leases -NotePropertyValue @() -Force }

  foreach ($dispatch in @($plan.dispatches)) {
    $now = (Get-Date).ToUniversalTime()
    $lease = [pscustomobject]@{
      shard=$dispatch.shard; repository=$dispatch.repository; execution_id=$dispatch.inputs.execution_id;
      work_item_id=$dispatch.inputs.work_item_id; collision_domain=$dispatch.inputs.collision_domain;
      idempotency_key=$dispatch.inputs.idempotency_key; state='LEASED'; acquired_at=$now.ToString('o');
      expires_at=$now.AddMinutes($LeaseMinutes).ToString('o'); run_id=$null; conclusion=$null
    }
    $leaseState.leases = @($leaseState.leases) + $lease
    [IO.File]::WriteAllText((Resolve-Path $Leases).Path, ($leaseState | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))

    Write-Host "DISPATCH $($dispatch.inputs.work_item_id) -> $($dispatch.repository)"
    gh workflow run $dispatch.workflow -R $dispatch.repository `
      -f execution_id=$dispatch.inputs.execution_id `
      -f work_item_id=$dispatch.inputs.work_item_id `
      -f project_id=$dispatch.inputs.project_id `
      -f generation_id=$dispatch.inputs.generation_id `
      -f input_sha=$dispatch.inputs.input_sha `
      -f collision_domain=$dispatch.inputs.collision_domain `
      -f idempotency_key=$dispatch.inputs.idempotency_key
    if ($LASTEXITCODE -ne 0) { $lease.state='DISPATCH_FAILED'; continue }

    Start-Sleep -Seconds 3
    $run = gh run list -R $dispatch.repository --workflow $dispatch.workflow --event workflow_dispatch --limit 1 --json databaseId,status,conclusion,createdAt | ConvertFrom-Json
    if (-not $run) { $lease.state='RUN_NOT_OBSERVED'; continue }
    $lease.run_id = $run[0].databaseId
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    do {
      $view = gh run view $lease.run_id -R $dispatch.repository --json status,conclusion | ConvertFrom-Json
      if ($view.status -eq 'completed') { break }
      Start-Sleep -Seconds $PollSeconds
    } while ((Get-Date) -lt $deadline)

    if ($view.status -ne 'completed') { $lease.state='TIMED_OUT'; continue }
    $lease.conclusion = $view.conclusion
    if ($view.conclusion -ne 'success') { $lease.state='FAILED'; continue }

    $target = Join-Path $Receipts $dispatch.inputs.execution_id
    New-Item -ItemType Directory -Force $target | Out-Null
    gh run download $lease.run_id -R $dispatch.repository -n "razzo-receipt-$($dispatch.inputs.execution_id)" -D $target
    if ($LASTEXITCODE -ne 0) { $lease.state='RECEIPT_MISSING'; continue }
    $receiptFile = Get-ChildItem $target -Filter '*.json' -File | Select-Object -First 1
    if (-not $receiptFile) { $lease.state='RECEIPT_MISSING'; continue }
    $receipt = Get-Content $receiptFile.FullName -Raw | ConvertFrom-Json
    if ($receipt.status -ne 'HEALTHY' -or $receipt.verification_state -ne 'DISPATCH_ENVELOPE_VERIFIED') {
      $lease.state='RECEIPT_INVALID'; continue
    }
    $lease.state='COMPLETED'; $lease.expires_at=(Get-Date).ToUniversalTime().ToString('o')
    Write-Host "COMPLETED $($dispatch.inputs.work_item_id) receipt=$($receiptFile.FullName)"
  }
  [IO.File]::WriteAllText((Resolve-Path $Leases).Path, ($leaseState | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
  $failed = @($leaseState.leases | Where-Object { $_.state -in @('DISPATCH_FAILED','RUN_NOT_OBSERVED','TIMED_OUT','FAILED','RECEIPT_MISSING','RECEIPT_INVALID') })
  if ($failed.Count -gt 0) { throw "HOMO NOVUS dispatch completed with $($failed.Count) failed lease(s)." }
  Write-Host "HOMO NOVUS PHASE 2 COMPLETE dispatches=$($plan.dispatch_count)"
}
finally {
  $mutex.ReleaseMutex(); $mutex.Dispose()
}
