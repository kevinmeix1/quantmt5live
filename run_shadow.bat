@echo off
REM == SAFE shadow run: computes & journals intended orders, sends NOTHING ==
REM Run this first to confirm the loop works against your live MT5 connection.
cd /d "%~dp0"
call .venv\Scripts\activate
quanthack live-trade ^
  --config configs\competition.toml ^
  --adapter mt5 ^
  --poll-seconds 60 ^
  --iterations 100000 ^
  --max-order-lots 0.25 ^
  --max-live-positions 2 ^
  --reduce-only-daily-loss-pct 0.0012 ^
  --reduce-only-rolling-sharpe -2.0 ^
  --live-metrics-csv outputs\live_metrics.csv ^
  --sentiment-snapshot outputs\fx_sentiment_snapshot.json ^
  --sentiment-conflict-threshold 1.25 ^
  --symbol-state-snapshot outputs\live_deal_attribution_latest.json ^
  --blocked-symbol-state cooldown_realized_drag ^
  --blocked-symbol-state observe ^
  --blocked-symbol-state keep_if_signal_aligned ^
  --small-only-symbol-state small_only_until_recovery ^
  --small-only-max-notional-usd 25000 ^
  --strategy champion_ensemble ^
  --strategy-map AUDUSD=macd_momentum ^
  --strategy-map EURGBP=champion_ensemble ^
  --strategy-map EURUSD=macd_momentum ^
  --strategy-map GBPUSD=champion_ensemble ^
  --strategy-map USDCAD=macd_momentum ^
  --strategy-map USDCHF=macd_momentum ^
  --strategy-map USDJPY=quality_trend ^
  --symbol AUDUSD --symbol EURGBP --symbol EURUSD --symbol GBPUSD ^
  --symbol USDCAD --symbol USDCHF --symbol USDJPY
pause
