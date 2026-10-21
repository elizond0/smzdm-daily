param(
    [string]$Title = "签到结果",
    [string]$Message = ""
)

# 用 Windows 自带的 Toast 通知，不依赖任何第三方模块。
# Windows 10 / 11 均可；若系统关闭了通知，调用不会报错但也不会弹出。

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

function Escape([string]$s) {
    if ($null -eq $s) { return "" }
    return $s.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
}

$xml = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>$(Escape $Title)</text>
      <text>$(Escape $Message)</text>
    </binding>
  </visual>
</toast>
"@

try {
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $doc
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    Write-Output "OK"
} catch {
    Write-Output "FAIL: $($_.Exception.Message)"
    exit 1
}
