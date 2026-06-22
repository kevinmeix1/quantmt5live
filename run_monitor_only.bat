@echo off
REM == SAFE monitor/research run: sends NO orders and starts no live-trade loop. ==
REM Use this laptop in monitor-only mode while another machine handles MT5 execution.
cd /d "%~dp0"
call .venv\Scripts\activate
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\live_supervisor.ps1 ^
  -Hours 120 ^
  -IntervalSeconds 300 ^
  -ResearchEveryCycles 3
pause
