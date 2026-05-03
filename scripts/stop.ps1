$ErrorActionPreference = "SilentlyContinue"

$ports = 48721..48820
$stopped = 0
foreach ($port in $ports) {
  $connections = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen
  foreach ($connection in $connections) {
    if ($connection.OwningProcess) {
      $process = Get-Process -Id $connection.OwningProcess
      if ($process.ProcessName -match "python|uvicorn") {
        Stop-Process -Id $process.Id -Force
        Write-Host "Stopped MineHost Helper manager on port $port."
        $stopped += 1
      }
    }
  }
}

if ($stopped -eq 0) {
  Write-Host "No MineHost Helper manager process was found on ports 48721-48820."
}
