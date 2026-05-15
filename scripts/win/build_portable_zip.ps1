# SPRi Newsletter — 동료 PC 용 Portable zip 빌드 스크립트
#
# 사용법 (메인 운영자 PC 의 PowerShell 에서):
#   PS> .\scripts\win\build_portable_zip.ps1
#   PS> .\scripts\win\build_portable_zip.ps1 -OutputDir "C:\release"
#   PS> .\scripts\win\build_portable_zip.ps1 -IncludeVenv      # .venv-win 동봉
#
# 산출물:
#   <OutputDir>\spri-newsletter-v<YYYYMMDD>.zip
#   <OutputDir>\spri-newsletter-v<YYYYMMDD>.zip.sha256
#
# 동작:
#   1. 임시 스테이징 디렉토리에 본 repo 복사 (제외 목록 적용)
#   2. data/db/*.csv 를 src/db.py 의 SHEET_HEADERS 기준 빈 파일로 재생성
#   3. data/manual_reports/, data/newsletters/, logs/, credentials/ 비우기
#   4. .env, google_token.json 등 시크릿 제외
#   5. (옵션) .venv-win 생성하여 동봉
#   6. zip 압축 + SHA-256 출력

param(
    [string]$OutputDir = ".\dist",
    [switch]$IncludeVenv = $false,
    [switch]$KeepStaging = $false
)

$ErrorActionPreference = "Stop"

# ── 경로 설정 ──
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Stamp = Get-Date -Format "yyyyMMdd"
$PackageName = "spri-newsletter-v$Stamp"
$Staging = Join-Path $env:TEMP "spri-build-$Stamp"
$OutputDirAbs = (New-Item -ItemType Directory -Force -Path $OutputDir).FullName
$ZipPath = Join-Path $OutputDirAbs "$PackageName.zip"

Write-Host "============================================================"
Write-Host " SPRi Newsletter Portable zip 빌드"
Write-Host " Repo:    $RepoRoot"
Write-Host " Staging: $Staging"
Write-Host " Output:  $ZipPath"
Write-Host "============================================================"

# ── 1. 스테이징 정리 ──
if (Test-Path $Staging) {
    Remove-Item -Recurse -Force $Staging
}
$StagingPkg = Join-Path $Staging $PackageName
New-Item -ItemType Directory -Force -Path $StagingPkg | Out-Null

# ── 2. repo 복사 (제외 패턴 적용) ──
$ExcludeDirs = @(".git", ".venv", ".venv-win", "__pycache__", ".pytest_cache",
                 "node_modules", "dist", "build", ".idea", ".vscode")
$ExcludeFiles = @(".env", "google_token.json",
                  "register_task.bat", "run_daily.bat", "task_schedule.xml")

Write-Host "[1/6] 코드 복사 중..."
robocopy $RepoRoot $StagingPkg /E /NFL /NDL /NJH /NJS /NP `
    /XD $ExcludeDirs `
    /XF $ExcludeFiles | Out-Null
# robocopy 는 정상 종료에도 1,3 등 비-0 코드를 반환하므로 명시적 체크 생략

# ── 3. credentials 디렉토리 비우기 ──
Write-Host "[2/6] credentials 비우는 중..."
$CredDir = Join-Path $StagingPkg "credentials"
if (Test-Path $CredDir) {
    Get-ChildItem $CredDir -File | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Force
}
else {
    New-Item -ItemType Directory -Force -Path $CredDir | Out-Null
}

# ── 4. 시드 데이터 비우기 ──
Write-Host "[3/6] data/, logs/ 비우는 중..."
$DataNewsletters = Join-Path $StagingPkg "data\newsletters"
$DataManualReports = Join-Path $StagingPkg "data\manual_reports"
$Logs = Join-Path $StagingPkg "logs"
foreach ($d in @($DataNewsletters, $DataManualReports, $Logs)) {
    if (Test-Path $d) {
        Get-ChildItem $d -Recurse -File | Remove-Item -Force -ErrorAction SilentlyContinue
    }
    else {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
    }
}

# ── 5. CSV 빈 파일 재생성 (SHEET_HEADERS 기준) ──
Write-Host "[4/6] data/db/*.csv 를 새 헤더로 재생성..."
$DbDir = Join-Path $StagingPkg "data\db"
New-Item -ItemType Directory -Force -Path $DbDir | Out-Null

# src/db.py 의 SHEET_HEADERS 와 동일한 헤더 정의 (zip 빌드 자급자족)
$Headers = @{
    "daily_articles.csv"   = "id,collected_at,title,url,description,source_name,published_at,used_in"
    "manual_articles.csv"  = "id,added_at,title,url,description,added_by"
    "article_archive.csv"  = "id,newsletter_date,newsletter_type,section,article_title,article_url"
    "newsletter_log.csv"   = "id,sent_at,type,article_count,recipient_count,status,error_message"
    "manual_reports.csv"   = "id,added_at,title,source_type,url,original_filename,file_path,text_path,summary,added_by"
}
foreach ($file in $Headers.Keys) {
    $path = Join-Path $DbDir $file
    # UTF-8 (no BOM) + 단일 헤더 라인
    [System.IO.File]::WriteAllText($path, $Headers[$file] + "`n", (New-Object System.Text.UTF8Encoding $false))
}

# ── 6. (옵션) venv 생성 ──
if ($IncludeVenv) {
    Write-Host "[5/6] .venv-win 생성 + 의존성 설치..."
    $VenvPath = Join-Path $StagingPkg ".venv-win"
    python -m venv $VenvPath
    $VenvPip = Join-Path $VenvPath "Scripts\pip.exe"
    & $VenvPip install --upgrade pip
    & $VenvPip install -r (Join-Path $StagingPkg "requirements.txt")
}
else {
    Write-Host "[5/6] .venv-win 동봉 건너뜀 (-IncludeVenv 미지정)"
}

# ── 7. zip 압축 ──
Write-Host "[6/6] zip 압축 중: $ZipPath"
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Path (Join-Path $Staging $PackageName) -DestinationPath $ZipPath -CompressionLevel Optimal

# ── 8. SHA-256 ──
$Sha = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash
$ShaPath = "$ZipPath.sha256"
"$Sha  $PackageName.zip" | Out-File -FilePath $ShaPath -Encoding ascii

Write-Host ""
Write-Host "============================================================"
Write-Host " 빌드 완료"
Write-Host "   ZIP    : $ZipPath"
Write-Host "   SHA256 : $Sha"
Write-Host "   SHA256 file: $ShaPath"
Write-Host "============================================================"

# ── 9. 정리 ──
if (-not $KeepStaging) {
    Remove-Item -Recurse -Force $Staging
}
else {
    Write-Host "[INFO] -KeepStaging 지정: 스테이징 디렉토리 유지 = $Staging"
}
