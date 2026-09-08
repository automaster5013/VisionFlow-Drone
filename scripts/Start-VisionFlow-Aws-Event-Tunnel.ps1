param(
  [Parameter(Mandatory=$true)][string]$IdentityFile,
  [Parameter(Mandatory=$true)][string]$KnownHostsFile
)
$ErrorActionPreference = 'Stop'
$existing = Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing[0].OwningProcess)"
  if ($owner.Name -eq 'ssh.exe' -and $owner.CommandLine -like '*127.0.0.1:18080:127.0.0.1:8080*' -and $owner.CommandLine -like '*ubuntu@15.165.56.192*') { Write-Output 'AWS event tunnel already running'; exit 0 }
  throw 'Port 18080 belongs to another process.'
}
$arguments = @('-N','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o',('UserKnownHostsFile="' + $KnownHostsFile + '"'),'-i',('"' + $IdentityFile + '"'),'-L','127.0.0.1:18080:127.0.0.1:8080','ubuntu@15.165.56.192')
$p = Start-Process -FilePath C:\Windows\System32\OpenSSH\ssh.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
Write-Output "Started AWS event tunnel, PID $($p.Id)"
