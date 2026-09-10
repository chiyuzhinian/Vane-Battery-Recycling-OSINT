<#
.SYNOPSIS
    数据源可达性与命中数实测 —— 回答"到底能不能搜到"。

.DESCRIPTION
    本机当前没有 Python 解释器（python 是 WindowsApps 商店占位符），
    因此这个验证脚本用 PowerShell + curl.exe 实现，开箱即跑。

    它逐个探测 sources/*.yaml 里登记的真实端点，输出：
      · HTTP 状态码 / 响应大小 / 耗时
      · 实际命中条数（能搜到多少）
      · 是否被反爬拦截

    判定标准：
      可达   = HTTP 200 且命中数 > 0
      被拦截 = HTTP 202 / 403 / 429
      失败   = 其他

.PARAMETER Json
    以 JSON 输出，便于接入 CI 或写入报告。

.EXAMPLE
    pwsh scripts/verify-sources.ps1
    pwsh scripts/verify-sources.ps1 -Json

.NOTES
    实测基线（2026-09-10）：
      US Federal Register API → 200，count=48
      EU SPARQL               → 200，查到 CELEX 32023R1542 + 6 个更正版本
      EU DG ENV 页面          → 200，84 KB
      EUR-Lex HTML            → 202（反爬）
      ECHA                    → 403（反爬）
#>

[CmdletBinding()]
param(
    [switch]$Json,
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$UA = 'BatteryRecyclingOSINT/1.0 (+research; contact: chiyuzhinian)'
$TmpDir = Join-Path $env:TEMP 'vane-osint-verify'
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

function Invoke-Probe {
    <# 返回 @{ Code; Size; ContentType; Body; Ms; Error } #>
    param(
        [string]$Name,
        [string]$Url,
        [string[]]$ExtraArgs = @(),
        [string]$Accept = 'text/html,application/json;q=0.9,*/*;q=0.8'
    )
    $out = Join-Path $TmpDir "$Name.body"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $meta = & curl.exe -s -o $out -w "%{http_code}|%{size_download}|%{content_type}" `
        --max-time $TimeoutSec -A $UA -H "Accept: $Accept" @ExtraArgs $Url 2>&1
    $sw.Stop()

    $code = $null; $size = $null; $ctype = $null
    if ($meta -match '^(\d{3})\|(\d+)\|(.*)$') {
        $code = [int]$Matches[1]; $size = [int]$Matches[2]; $ctype = $Matches[3]
    }

    $body = ''
    if (Test-Path $out) {
        $body = Get-Content $out -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($null -eq $body) { $body = '' }
    }

    [pscustomobject]@{
        Name        = $Name
        Url         = $Url
        Code        = $code
        Size        = $size
        ContentType = $ctype
        Ms          = [int]$sw.ElapsedMilliseconds
        Body        = $body
        Error       = ($meta -join ' ')
    }
}

function New-Result {
    param($Probe, [string]$Region, [string]$SourceId, [int]$Hits, [string]$Verdict, [string]$Note)
    [pscustomobject]@{
        region    = $Region
        source_id = $SourceId
        url       = $Probe.Url
        http      = $Probe.Code
        ms        = $Probe.Ms
        hits      = $Hits
        verdict   = $Verdict
        note      = $Note
    }
}

$results = New-Object System.Collections.Generic.List[object]

# ============================================================
# 1) 美国 · Federal Register API（无需 API Key）
# ============================================================
Write-Host "`n[1/5] 美国 Federal Register API ..." -ForegroundColor Cyan
$frUrl = 'https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=battery+recycling&conditions%5Bagencies%5D%5B%5D=energy-department&per_page=3&order=newest'
$p = Invoke-Probe -Name 'us_fr' -Url $frUrl -Accept 'application/json'
$hits = 0; $note = ''
if ($p.Code -eq 200 -and $p.Body) {
    try {
        $j = $p.Body | ConvertFrom-Json
        $hits = [int]$j.count
        $note = "机构=DOE, 最新=$($j.results[0].publication_date), 总页数=$($j.total_pages)"
    } catch { $note = "JSON 解析失败: $($_.Exception.Message)" }
}
$verdict = if ($p.Code -eq 200 -and $hits -gt 0) { 'REACHABLE' } elseif ($p.Code -in 202,403,429) { 'BLOCKED' } else { 'FAILED' }
$results.Add((New-Result $p 'US' 'us_federal_register' $hits $verdict $note))

# ============================================================
# 2) 欧盟 · Publications Office SPARQL（官方机器接口）
# ============================================================
Write-Host "[2/5] 欧盟 SPARQL（CELEX 32023R1542 电池法规）..." -ForegroundColor Cyan
$sparql = 'https://publications.europa.eu/webapi/rdf/sparql'
$qFile = Join-Path $TmpDir 'battery_reg.rq'
$query = 'PREFIX cdm: <http://publications.europa.eu/ontology/cdm#> SELECT DISTINCT ?work ?celex WHERE { ?work cdm:resource_legal_id_celex ?celex . FILTER(STRSTARTS(STR(?celex), "32023R1542")) } LIMIT 20'
# 注意：必须无 BOM 写入，带 BOM 会让 Virtuoso 报 "Bad character"
[System.IO.File]::WriteAllText($qFile, $query, [System.Text.UTF8Encoding]::new($false))

$p = Invoke-Probe -Name 'eu_sparql' -Url $sparql -Accept 'application/sparql-results+json' -ExtraArgs @(
    '-G',
    '--data-urlencode', "query@$qFile",
    '--data-urlencode', 'format=application/sparql-results+json'
)
$hits = 0; $note = ''
if ($p.Code -eq 200 -and $p.Body) {
    try {
        $j = $p.Body | ConvertFrom-Json
        $celexes = @($j.results.bindings | ForEach-Object { $_.celex.value } | Sort-Object -Unique)
        $hits = $celexes.Count
        $corrigenda = @($celexes | Where-Object { $_ -match 'R\(\d+\)$' })
        $note = "命中 $hits 个 CELEX，其中更正版本 $($corrigenda.Count) 个"
    } catch { $note = "SPARQL JSON 解析失败" }
}
$verdict = if ($p.Code -eq 200 -and $hits -gt 0) { 'REACHABLE' } elseif ($p.Code -in 202,403,429) { 'BLOCKED' } else { 'FAILED' }
$results.Add((New-Result $p 'EU' 'eu_eurlex_sparql' $hits $verdict $note))

# ============================================================
# 3) 欧盟 · DG ENV 电池专题页（可 diff 监测）
# ============================================================
Write-Host "[3/5] 欧盟 DG ENV 电池专题页 ..." -ForegroundColor Cyan
$p = Invoke-Probe -Name 'eu_dgenv' -Url 'https://environment.ec.europa.eu/topics/waste-and-recycling/batteries_en'
$hasLaw = $p.Body -match 'Batteries Regulation|2023/1542'
$note = if ($hasLaw) { '页面含法规链接，可用于变更 diff 监测' } else { '页面结构可能已变' }
$verdict = if ($p.Code -eq 200) { 'REACHABLE' } elseif ($p.Code -in 202,403,429) { 'BLOCKED' } else { 'FAILED' }
$results.Add((New-Result $p 'EU' 'eu_dg_env_batteries' ([int]($p.Code -eq 200)) $verdict $note))

# ============================================================
# 4) 欧盟 · EUR-Lex HTML 正文（预期被反爬）
# ============================================================
Write-Host "[4/5] 欧盟 EUR-Lex HTML 正文（预期 202 反爬）..." -ForegroundColor Cyan
$p = Invoke-Probe -Name 'eu_eurlex_html' -Url 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1542'
$verdict = switch ($p.Code) { 200 { 'REACHABLE' } { $_ -in 202,403,429 } { 'BLOCKED' } default { 'FAILED' } }
$results.Add((New-Result $p 'EU' 'eu_eurlex_html' 0 $verdict '已知反爬：改用 SPARQL 或 Playwright'))

# ============================================================
# 5) 欧盟 · ECHA（预期 403）
# ============================================================
Write-Host "[5/5] 欧盟 ECHA（预期 403 反爬）..." -ForegroundColor Cyan
$p = Invoke-Probe -Name 'eu_echa' -Url 'https://echa.europa.eu/regulations/batteries-regulation'
$verdict = switch ($p.Code) { 200 { 'REACHABLE' } { $_ -in 202,403,429 } { 'BLOCKED' } default { 'FAILED' } }
$results.Add((New-Result $p 'EU' 'eu_echa' 0 $verdict '已知反爬：降级为 site: 定向搜索'))

# ============================================================
# 汇总
# ============================================================
if ($Json) {
    $results | ConvertTo-Json -Depth 4
    exit 0
}

Write-Host "`n════════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host " 数据源可达性实测报告  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "════════════════════════════════════════════════════════════════════" -ForegroundColor Yellow

$icon = @{ REACHABLE = '✅'; BLOCKED = '🚫'; FAILED = '❌' }
$results | ForEach-Object {
    $i = $icon[$_.verdict]
    "{0} [{1}] {2,-24} HTTP {3,-4} {4,6}ms  命中 {5,-5} {6}" -f `
        $i, $_.region, $_.source_id, $_.http, $_.ms, $_.hits, $_.note
} | Write-Host

$ok      = @($results | Where-Object verdict -eq 'REACHABLE').Count
$blocked = @($results | Where-Object verdict -eq 'BLOCKED').Count
$failed  = @($results | Where-Object verdict -eq 'FAILED').Count

Write-Host ""
Write-Host (" 汇总：✅ 可达 {0} 个 | 🚫 被反爬 {1} 个 | ❌ 失败 {2} 个" -f $ok, $blocked, $failed) -ForegroundColor Yellow

if ($failed -gt 0) {
    Write-Host "`n ⚠️ 有源失败，请检查网络或源站变更。" -ForegroundColor Red
    exit 2
}
Write-Host "`n 下一步：可达的源可直接接入采集；被反爬的源走 SPARQL / Playwright / site: 搜索替代。" -ForegroundColor Green
exit 0
