param(
  [int]$Hours = 6,
  [double]$MaxOrderLots = 0.25
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"

$OutLog = Join-Path $Root "outputs\live_trading_stdout.log"
$ErrLog = Join-Path $Root "outputs\live_trading_stderr.log"
$GuardLog = Join-Path $Root "outputs\live_guard.log"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Quanthack = Join-Path $Root ".venv\Scripts\quanthack.exe"
$LiveArgs = "live-trade --config configs\competition.toml --adapter mt5 --poll-seconds 60 --iterations 100000 --max-order-lots $MaxOrderLots --max-live-positions 2 --reduce-only-daily-loss-pct 0.0012 --reduce-only-rolling-sharpe -2.0 --live-metrics-csv outputs\live_metrics.csv --sentiment-snapshot outputs\fx_sentiment_snapshot.json --sentiment-conflict-threshold 1.25 --symbol-state-snapshot outputs\live_deal_attribution_latest.json --blocked-symbol-state cooldown_realized_drag --blocked-symbol-state observe --blocked-symbol-state keep_if_signal_aligned --small-only-symbol-state small_only_until_recovery --small-only-max-notional-usd 25000 --strategy champion_ensemble --strategy-map AUDUSD=macd_momentum --strategy-map EURGBP=champion_ensemble --strategy-map EURUSD=macd_momentum --strategy-map GBPUSD=champion_ensemble --strategy-map USDCAD=macd_momentum --strategy-map USDCHF=macd_momentum --symbol AUDUSD --symbol EURGBP --symbol EURUSD --symbol GBPUSD --symbol USDCAD --symbol USDCHF --i-understand-live-orders"

function Write-GuardLog($Message) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $GuardLog) | Out-Null
  $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
  Add-Content -Path $GuardLog -Value "[$stamp] $Message"
}

function Get-LiveProcess {
  Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*live-trade*--i-understand-live-orders*" -and
    $_.CommandLine -notlike "*Get-CimInstance*"
  }
}

function Start-LiveProcess {
  if (Get-LiveProcess) {
    return
  }
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  if (Test-Path -LiteralPath $OutLog) {
    Move-Item -LiteralPath $OutLog -Destination (Join-Path $Root "outputs\live_trading_stdout_guard_restart_$stamp.log")
  }
  if (Test-Path -LiteralPath $ErrLog) {
    Move-Item -LiteralPath $ErrLog -Destination (Join-Path $Root "outputs\live_trading_stderr_guard_restart_$stamp.log")
  }
  $p = Start-Process -FilePath $Quanthack -ArgumentList $LiveArgs -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru
  Write-GuardLog "restarted live process pid=$($p.Id)"
}

function Get-Mt5StatusJson {
  $script = @'
import json
import MetaTrader5 as mt5

terminal = r"C:\Program Files\MetaTrader 5\terminal64.exe"
status = {"ok": False}
if not mt5.initialize(path=terminal, timeout=180000):
    status["error"] = f"initialize failed: {mt5.last_error()}"
else:
    try:
        term = mt5.terminal_info()
        acct = mt5.account_info()
        positions = mt5.positions_get()
        status.update({
            "ok": True,
            "terminal_trade_allowed": bool(getattr(term, "trade_allowed", False)),
            "equity": float(getattr(acct, "equity", 0.0) or 0.0),
            "balance": float(getattr(acct, "balance", 0.0) or 0.0),
            "margin": float(getattr(acct, "margin", 0.0) or 0.0),
            "free_margin": float(getattr(acct, "margin_free", 0.0) or 0.0),
            "margin_level": float(getattr(acct, "margin_level", 0.0) or 0.0),
            "positions_count": None if positions is None else len(positions),
            "positions": [] if not positions else [
                {
                    "ticket": int(p.ticket),
                    "symbol": str(p.symbol),
                    "volume": float(p.volume),
                    "type": int(p.type),
                    "price_open": float(p.price_open),
                    "profit": float(p.profit),
                }
                for p in positions
            ],
            "last_error": mt5.last_error(),
        })
    finally:
        mt5.shutdown()
print(json.dumps(status, sort_keys=True))
'@
  return ($script | & $Python -)
}

function Flatten-Live($Reason) {
  Write-GuardLog "flatten triggered: $Reason"
  & $Quanthack mt5-flatten --config configs\competition.toml --i-understand-live-orders | ForEach-Object {
    Write-GuardLog "flatten: $_"
  }
}

$Deadline = (Get-Date).AddHours($Hours)
Write-GuardLog "guard started hours=$Hours max_order_lots=$MaxOrderLots"

while ((Get-Date) -lt $Deadline) {
  try {
    Start-LiveProcess
    $json = Get-Mt5StatusJson
    Write-GuardLog "mt5 $json"
    $metrics = & $Python scripts\live_metrics.py
    Write-GuardLog "metrics $metrics"
    $status = $json | ConvertFrom-Json
    $metricStatus = $metrics | ConvertFrom-Json
    if ($status.ok -and $status.terminal_trade_allowed -eq $false) {
      Write-GuardLog "terminal trading disabled; live process cannot place new orders"
    }
    if ($status.ok -and $null -ne $status.positions_count) {
      if ($status.margin_level -gt 0 -and $status.margin_level -lt 1000) {
        Flatten-Live "margin level below 1000%"
      } elseif ($metricStatus.day_pnl -lt -1500) {
        Flatten-Live "day P/L below -1500 recovery-mode stop"
      } elseif ($metricStatus.day_pnl -lt -1200 -and $metricStatus.rolling_sharpe_15 -lt -2) {
        Flatten-Live "negative P/L with poor rolling Sharpe"
      } elseif ($status.equity -gt 0 -and $status.equity -lt 985000) {
        Flatten-Live "equity below 985000 survival stop"
      }
    }
  } catch {
    Write-GuardLog "guard error: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 60
}

Write-GuardLog "guard finished"
