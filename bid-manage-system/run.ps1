$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process powershell.exe -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File',(Join-Path $Root 'backend\run.ps1')
Start-Sleep -Seconds 2
Start-Process cmd.exe -ArgumentList '/k','npm.cmd run dev' -WorkingDirectory (Join-Path $Root 'frontend')
Write-Host "Bid Manage System started"
Write-Host "Frontend: http://127.0.0.1:9012"
Write-Host "Backend:  http://127.0.0.1:9013"
