param(
  [int]$Hours = 24,
  [int]$IntervalSeconds = 300,
  [int]$ResearchEveryCycles = 3
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$SupervisorLog = Join-Path $Root "outputs\live_supervisor.log"

function Write-SupervisorLog($Message) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SupervisorLog) | Out-Null
  $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
  Add-Content -Path $SupervisorLog -Value "[$stamp] $Message"
}

function Invoke-And-Log($Label, $CommandArgs) {
  try {
    $output = & $Python @CommandArgs 2>&1
    foreach ($line in $output) {
      Write-SupervisorLog "${Label}: $line"
    }
  } catch {
    Write-SupervisorLog "${Label} error: $($_.Exception.Message)"
  }
}

$Deadline = (Get-Date).AddHours($Hours)
Write-SupervisorLog "supervisor started hours=$Hours interval_seconds=$IntervalSeconds research_every_cycles=$ResearchEveryCycles"

$Cycle = 0
while ((Get-Date) -lt $Deadline) {
  $Cycle += 1
  Invoke-And-Log "sentiment" @("scripts\update_fx_sentiment.py")
  Invoke-And-Log "deal_attribution" @("scripts\live_deal_attribution.py")
  Invoke-And-Log "pair_analysis" @("scripts\live_pair_analysis.py")
  Invoke-And-Log "strategy_diagnostics" @("scripts\live_strategy_diagnostics.py")
  Invoke-And-Log "directional_probe_diag" @(
    "scripts\live_strategy_diagnostics.py",
    "--allocation-profile", "directional_probe",
    "--output-json", "outputs\live_strategy_diagnostics_directional_probe_latest.json",
    "--history-jsonl", "outputs\live_strategy_diagnostics_directional_probe_history.jsonl",
    "--output-text", "outputs\live_strategy_diagnostics_directional_probe_latest.txt"
  )
  Invoke-And-Log "candidate_diag_eurgbp_cross_rate" @(
    "scripts\live_strategy_diagnostics.py",
    "--strategy-map", "AUDUSD=macd_momentum",
    "--strategy-map", "EURGBP=cross_rate_reversion",
    "--strategy-map", "EURUSD=macd_momentum",
    "--strategy-map", "GBPUSD=champion_ensemble",
    "--strategy-map", "USDCAD=macd_momentum",
    "--strategy-map", "USDCHF=macd_momentum",
    "--output-json", "outputs\candidate_eurgbp_cross_rate_live_strategy_diagnostics_latest.json",
    "--history-jsonl", "outputs\candidate_eurgbp_cross_rate_live_strategy_diagnostics_history.jsonl",
    "--output-text", "outputs\candidate_eurgbp_cross_rate_live_strategy_diagnostics_latest.txt"
  )
  Invoke-And-Log "candidate_diag_all_quality_trend" @(
    "scripts\live_strategy_diagnostics.py",
    "--strategy-map", "AUDUSD=quality_trend",
    "--strategy-map", "EURGBP=quality_trend",
    "--strategy-map", "EURUSD=quality_trend",
    "--strategy-map", "GBPUSD=quality_trend",
    "--strategy-map", "USDCAD=quality_trend",
    "--strategy-map", "USDCHF=quality_trend",
    "--allocation-profile", "directional_probe",
    "--output-json", "outputs\candidate_all_quality_trend_live_strategy_diagnostics_latest.json",
    "--history-jsonl", "outputs\candidate_all_quality_trend_live_strategy_diagnostics_history.jsonl",
    "--output-text", "outputs\candidate_all_quality_trend_live_strategy_diagnostics_latest.txt"
  )
  Invoke-And-Log "candidate_diag_best_symbol_mix" @(
    "scripts\live_strategy_diagnostics.py",
    "--strategy-map", "AUDUSD=volatility_squeeze",
    "--strategy-map", "EURGBP=volatility_squeeze",
    "--strategy-map", "EURUSD=quality_trend",
    "--strategy-map", "GBPUSD=asset_adaptive_dual_squeeze",
    "--strategy-map", "USDCAD=volatility_squeeze",
    "--strategy-map", "USDCHF=macd_momentum",
    "--allocation-profile", "directional_probe",
    "--output-json", "outputs\candidate_best_symbol_mix_live_strategy_diagnostics_latest.json",
    "--history-jsonl", "outputs\candidate_best_symbol_mix_live_strategy_diagnostics_history.jsonl",
    "--output-text", "outputs\candidate_best_symbol_mix_live_strategy_diagnostics_latest.txt"
  )
  Invoke-And-Log "candidate_watchlist" @(
    "scripts\live_candidate_watchlist.py",
    "--candidates-csv", "outputs\backtests\live_watch_cross_rate_live6_h4_strict.csv",
    "--candidate-strategy", "cross_rate_reversion",
    "--default-live-strategy", "champion_ensemble",
    "--live-strategy-map", "AUDUSD=macd_momentum",
    "--live-strategy-map", "EURGBP=champion_ensemble",
    "--live-strategy-map", "EURUSD=macd_momentum",
    "--live-strategy-map", "GBPUSD=champion_ensemble",
    "--live-strategy-map", "USDCAD=macd_momentum",
    "--live-strategy-map", "USDCHF=macd_momentum",
    "--min-quality-score", "1.0",
    "--output-json", "outputs\live_candidate_watchlist_latest.json",
    "--output-text", "outputs\live_candidate_watchlist_latest.txt"
  )
  if (($ResearchEveryCycles -gt 0) -and (($Cycle % $ResearchEveryCycles) -eq 0)) {
    Invoke-And-Log "research_cycle" @(
      "scripts\live_research_cycle.py",
      "--basket-allocation-profile", "directional_probe",
      "--force-qualify-mode"
    )
  }
  Invoke-And-Log "status_summary" @("scripts\live_status_summary.py")
  Start-Sleep -Seconds $IntervalSeconds
}

Write-SupervisorLog "supervisor finished"
