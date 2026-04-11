$ErrorActionPreference = 'Stop'
$taskName = 'SPRi_Daily_Newsletter'

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$wp = New-Object System.Security.Principal.WindowsPrincipal($currentIdentity)
$isAdmin = $wp.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host ("Current user: {0}" -f $currentIdentity.Name)
Write-Host ("IsAdmin: {0}" -f $isAdmin)
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "[INFO] Not running as administrator. Re-launching with UAC elevation..." -ForegroundColor Yellow
    Write-Host "Please click 'Yes' on the UAC prompt that appears."
    $psExe = (Get-Process -Id $PID).Path
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', "`"$PSCommandPath`"")
    try {
        Start-Process -FilePath $psExe -ArgumentList $argList -Verb RunAs
        Write-Host "Elevated window launched. Check the new window for results."
    } catch {
        Write-Host "[ERROR] UAC elevation failed or was cancelled: $_" -ForegroundColor Red
        Write-Host "Manually open 'Windows PowerShell' -> 'Run as administrator' and run:"
        Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    }
    exit 0
}

Write-Host ""
Write-Host "Step 1: Export current task XML"
$xmlStr = Export-ScheduledTask -TaskName $taskName

$backupPath = Join-Path $PSScriptRoot 'spri_task_backup.xml'
[System.IO.File]::WriteAllText($backupPath, $xmlStr, [System.Text.Encoding]::Unicode)
Write-Host "  Backup saved: $backupPath"

[xml]$xml = $xmlStr
$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
$nsUri = 'http://schemas.microsoft.com/windows/2004/02/mit/task'

Write-Host "Step 2: Change LogonType to InteractiveToken (no stored password)"
$logonTypeNode = $xml.SelectSingleNode('//t:Principal/t:LogonType', $ns)
if ($logonTypeNode) { $logonTypeNode.InnerText = 'InteractiveToken' }

$userIdNode = $xml.SelectSingleNode('//t:Principal/t:UserId', $ns)
$userIdText = if ($userIdNode) { $userIdNode.InnerText } else { '' }

Write-Host "Step 3: Add LogonTrigger (5-minute delay)"
$triggersNode = $xml.SelectSingleNode('//t:Triggers', $ns)

$logonTrigger = $xml.CreateElement('LogonTrigger', $nsUri)
$enabledEl = $xml.CreateElement('Enabled', $nsUri); $enabledEl.InnerText = 'true'
$logonTrigger.AppendChild($enabledEl) | Out-Null
$delayEl = $xml.CreateElement('Delay', $nsUri); $delayEl.InnerText = 'PT5M'
$logonTrigger.AppendChild($delayEl) | Out-Null
if ($userIdText) {
    $uidEl = $xml.CreateElement('UserId', $nsUri); $uidEl.InnerText = $userIdText
    $logonTrigger.AppendChild($uidEl) | Out-Null
}
$triggersNode.AppendChild($logonTrigger) | Out-Null

Write-Host "Step 4: Add daily repetition trigger (start 08:00, every 3h for 10h)"
$dailyTrigger = $xml.CreateElement('CalendarTrigger', $nsUri)

$sbEl = $xml.CreateElement('StartBoundary', $nsUri); $sbEl.InnerText = '2026-04-08T08:00:00'
$dailyTrigger.AppendChild($sbEl) | Out-Null

$enabledEl2 = $xml.CreateElement('Enabled', $nsUri); $enabledEl2.InnerText = 'true'
$dailyTrigger.AppendChild($enabledEl2) | Out-Null

$repEl = $xml.CreateElement('Repetition', $nsUri)
$intEl = $xml.CreateElement('Interval', $nsUri); $intEl.InnerText = 'PT3H'
$repEl.AppendChild($intEl) | Out-Null
$durEl = $xml.CreateElement('Duration', $nsUri); $durEl.InnerText = 'PT10H'
$repEl.AppendChild($durEl) | Out-Null
$stopEl = $xml.CreateElement('StopAtDurationEnd', $nsUri); $stopEl.InnerText = 'true'
$repEl.AppendChild($stopEl) | Out-Null
$dailyTrigger.AppendChild($repEl) | Out-Null

$sbdEl = $xml.CreateElement('ScheduleByDay', $nsUri)
$diEl = $xml.CreateElement('DaysInterval', $nsUri); $diEl.InnerText = '1'
$sbdEl.AppendChild($diEl) | Out-Null
$dailyTrigger.AppendChild($sbdEl) | Out-Null

$triggersNode.AppendChild($dailyTrigger) | Out-Null

$newXmlStr = $xml.OuterXml

Write-Host ""
Write-Host "--- Modified XML ---"
Write-Host $newXmlStr
Write-Host "--------------------"
Write-Host ""

Write-Host "Step 5: Re-register task (Register-ScheduledTask -Force)"
Register-ScheduledTask -TaskName $taskName -Xml $newXmlStr -Force | Out-Null

Write-Host ""
Write-Host "=== Registered. Current triggers ==="
(Get-ScheduledTask -TaskName $taskName).Triggers | Format-List *

Write-Host ""
Write-Host "=== Task info ==="
Get-ScheduledTaskInfo -TaskName $taskName | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime, State
