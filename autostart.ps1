# Добавя (или маха с -Remove) Universal Keyboard в автоматичното стартиране на Windows.
#   powershell -ExecutionPolicy Bypass -File autostart.ps1
#   powershell -ExecutionPolicy Bypass -File autostart.ps1 -Remove
param([switch]$Remove)

$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Universal Keyboard.lnk'
if ($Remove) {
    if (Test-Path $lnk) { Remove-Item $lnk }
    Write-Host 'Махнато от автоматичното стартиране.'
    return
}
$pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
$script = Join-Path $PSScriptRoot 'universal_keyboard.pyw'
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = $pythonw
$sh.Arguments = '"' + $script + '"'
$sh.WorkingDirectory = $PSScriptRoot
$sh.Save()
Write-Host "Добавено: $lnk"
