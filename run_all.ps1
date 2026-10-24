# Полный цикл проекта Warehouse & Logistics Analytics.
# Запуск из корня проекта:  .\run_all.ps1
# Пропустить отдельные шаги:  .\run_all.ps1 -SkipGenerate

param(
    [switch]$SkipGenerate,
    [switch]$SkipLoad
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Виртуальное окружение не найдено. Создайте его:" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

function Invoke-Step {
    param([string]$Title, [string]$Script)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
    & $python $Script 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Шаг завершился с ошибкой: $Script" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

if (-not $SkipGenerate) {
    Invoke-Step "ШАГ 1/5  Генерация синтетических данных" "generator\generate_data.py"
}

Invoke-Step "ШАГ 2/5  Проверка качества и очистка" "analytics\data_quality.py"

if (-not $SkipLoad) {
    Invoke-Step "ШАГ 3/5  Загрузка в PostgreSQL" "etl\load_data.py"
}

Invoke-Step "ШАГ 4/5  SQL-анализ" "sql\run_queries.py"
Invoke-Step "ШАГ 5/5  Графики, гипотезы, витрины" "analytics\analysis.py"

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "ГОТОВО" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "Графики:        reports\figures\"
Write-Host "Гипотезы:       reports\hypothesis_tests.csv"
Write-Host "Витрины BI:     data\powerbi\"
Write-Host "Отчёт качества: data\processed\quality_report.csv"
