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
  --max-order-lots 0.10
pause
