@echo off
REM == KILL-SWITCH: close ALL open MT5 positions immediately. ==
REM Without --i-understand-live-orders this only REPORTS what it would close.
REM Add --i-understand-live-orders (already below) to actually close.
cd /d "%~dp0"
call .venv\Scripts\activate
quanthack mt5-flatten --config configs\competition.toml --i-understand-live-orders
pause
