<#
.SYNOPSIS
    用 curl 批量探测 URL（TLS 栈与 Python 不同，用于交叉验证）。

.DESCRIPTION
    Python 的 httpx 走 OpenSSL，部分国内政府和欧盟站点会因
    非标准 EC 曲线（bad ecpoint）或 TLS 记录异常而失败；
    curl.exe 在 Windows 上走 SChannel，成功率高得多。

    因此本脚本用于：判定某个源到底是"真的不可达"还是"只是 Python 连不上"。

.PARAMETER UrlFile
    每行一个 URL 的文本文件。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\probe-urls.ps1 -UrlFile .\urls.txt
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UrlFile,
    [int]$TimeoutSec = 25,
    [string]$UserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path $UrlFile)) {
    Write-Error "找不到 URL 文件：$UrlFile"
    exit 1
}

$urls = Get-Content $UrlFile -Encoding UTF8 |
    Where-Object { $_ -and $_.Trim() -and -not $_.Trim().StartsWith('#') } |
    ForEach-Object { $_.Trim() }

Write-Host ""
Write-Host "curl 批量探测（共 $($urls.Count) 个）" -ForegroundColor Yellow
Write-Host ("─" * 96)

foreach ($u in $urls) {
    $out = Join-Path $env:TEMP 'probe-body.tmp'
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $meta = & curl.exe -s -o $out -w "%{http_code}|%{size_download}|%{content_type}" `
        --max-time $TimeoutSec -L -A $UserAgent $u 2>&1
    $sw.Stop()

    $code = 'ERR'; $size = 0; $ctype = ''
    if ($meta -match '^(\d{3})\|(\d+)\|(.*)$') {
        $code = $Matches[1]; $size = [int]$Matches[2]; $ctype = $Matches[3]
    }

    $icon = switch ($code) {
        '200' { '✅' }
        '202' { '🚫' }
        '403' { '🚫' }
        '404' { '⚠️' }
        '429' { '🚫' }
        default { '❌' }
    }
    $kb = [math]::Round($size / 1024, 1)
    Write-Host ("{0} {1,-4} {2,8} KB  {3,6}ms  {4}" -f $icon, $code, $kb, $sw.ElapsedMilliseconds, $u)
}
Write-Host ("─" * 96)
Write-Host ""
