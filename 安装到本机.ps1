param([string]$InstallRoot = '', [string]$ShortcutFolder = '')
$ErrorActionPreference = 'Stop'
try {
    $sourceDir = [IO.Path]::GetFullPath($PSScriptRoot)
    if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\OfflineVoiceLedger' }
    $installDir = [IO.Path]::GetFullPath($InstallRoot)
    if ($sourceDir.TrimEnd('\') -ne $installDir.TrimEnd('\')) {
        if (Get-Process -Name '离线语音记账' -ErrorAction SilentlyContinue) {
            throw '请先关闭离线语音记账程序，再进行安装。'
        }
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        $copyItems = @('离线语音记账.exe','_internal','模型','许可证','使用说明.txt','更新说明.txt','安装到本机.cmd','安装到本机.ps1')
        foreach ($itemName in $copyItems) {
            $itemPath = Join-Path $sourceDir $itemName
            if (Test-Path -LiteralPath $itemPath) {
                Copy-Item -LiteralPath $itemPath -Destination $installDir -Recurse -Force
            }
        }
    }
    $desktopDir = if ($ShortcutFolder) { [IO.Path]::GetFullPath($ShortcutFolder) } else { [Environment]::GetFolderPath('Desktop') }
    New-Item -ItemType Directory -Force -Path $desktopDir | Out-Null
    $shortcutPath = Join-Path $desktopDir '离线语音记账.lnk'
    $shellObject = New-Object -ComObject WScript.Shell
    $shortcutObject = $shellObject.CreateShortcut($shortcutPath)
    $shortcutObject.TargetPath = Join-Path $installDir '离线语音记账.exe'
    $shortcutObject.WorkingDirectory = $installDir
    $shortcutObject.Description = '无需联网的语音记账应用'
    $shortcutObject.Save()
    Write-Host ('安装完成：' + $installDir)
    Write-Host '请双击桌面的“离线语音记账”快捷方式使用。'
} catch {
    Write-Host ('安装未完成：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
