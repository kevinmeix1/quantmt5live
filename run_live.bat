@echo off
REM == LIVE run: PLACES REAL ORDERS on the MT5 account. ==
REM Only run after: (1) mt5-probe OK, (2) run_shadow.bat looked correct,
REM (3) one tiny manual-ticket order confirmed. Start with a SMALL --max-order-lots.
cd /d "%~dp0"
call .venv\Scripts\activate
quanthack live-trade ^
  --config configs\competition.toml ^
  --adapter mt5 ^
  --poll-seconds 60 ^
  --iterations 100000 ^
  --max-order-lots 0.20 ^
  --i-understand-live-orders
pause
