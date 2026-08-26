# Pings the SAP dev host through the AnyConnect tunnel every 10 seconds so
# the ASA/head-end idle-timeout never triggers, and drops get logged almost
# immediately. AnyConnect's own "Connected" status doesn't reflect a dead
# tunnel, so this is a workaround, not a real fix.

$ErrorActionPreference = "SilentlyContinue"
$logFile = Join-Path $PSScriptRoot "..\vpn_keepalive.log"

while ($true) {
    $result = Test-NetConnection -ComputerName "srv-devecc01" -Port 3301 -WarningAction SilentlyContinue
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $status = if ($result.TcpTestSucceeded) { "OK" } else { "UNREACHABLE" }
    Add-Content -Path $logFile -Value "$timestamp  $status"
    Start-Sleep -Seconds 10
}
