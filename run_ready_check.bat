@echo off
REM == NO-ORDER readiness check before starting live trading. ==
REM Safe to run before 22:00 BST: probes MT5 and runs one shadow iteration only.
cd /d "%~dp0"
call .venv\Scripts\activate

quanthack check-environment
if errorlevel 1 goto fail

quanthack preflight
if errorlevel 1 goto fail

quanthack show-mode
if errorlevel 1 goto fail

quanthack mt5-probe --confirm-read-only-mt5 ^
  --symbol AUDUSD --symbol USDCHF --symbol XAUUSD
if errorlevel 1 goto fail

quanthack live-trade ^
  --config configs\competition.toml ^
  --adapter mt5 ^
  --iterations 1 ^
  --poll-seconds 0 ^
  --max-order-lots 0.05 ^
  --strategy multi_horizon_momentum ^
  --symbol AUDUSD --symbol USDCHF --symbol XAUUSD
if errorlevel 1 goto fail

echo.
echo Ready check completed. No live orders were sent.
pause
exit /b 0

:fail
echo.
echo Ready check failed. Do not start run_live.bat until this is fixed.
pause
exit /b 1
