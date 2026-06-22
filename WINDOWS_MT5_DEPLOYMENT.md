# Windows + MT5 Live Deployment Guide (quantmt5live)

This folder is the live-trading build. It keeps everything from `quanthackclaude`
(validated strategy recipe, competition-safe risk config, resilient live loop)
and adds a **real MT5 order executor** (`Mt5LiveExecutor`) plus a gated
`live-trade` CLI.

> ⚠️ **Honest status.** The order *logic* (lot sizing, BUY/SELL direction,
> position reconciliation, max-lot cap, shadow/live gate) is unit-tested with a
> fake MT5 module (`tests/test_mt5_executor.py`, 6 tests). The actual
> `MetaTrader5.order_send` path **has not been run** — `MetaTrader5` is
> Windows-only and could not be executed on the build machine. **Validate on
> Windows with the sequence below before trusting it with size.**

---

## 1. One-time Windows setup

1. Install **Python 3.11 (64-bit)** from python.org — same bitness as your MT5
   terminal (almost always 64-bit). Tick "Add python.exe to PATH".
2. Install the **MetaTrader 5 terminal**, log in to the competition account
   (Login / Password / Server from the organizer), and in
   **Tools → Options → Expert Advisors** tick **"Allow algorithmic trading"**.
   Also click the **"Algo Trading"** toolbar button so it's green.
3. Open **PowerShell** in this folder and create an environment:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install -U pip
   pip install -e ".[mt5]"        # installs the package + MetaTrader5
   ```
4. Create your credentials file (do NOT commit it):
   ```powershell
   copy .env.example .env
   notepad .env
   ```
   Fill in `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, and `MT5_TERMINAL_PATH`
   (e.g. `C:\Program Files\MetaTrader 5\terminal64.exe`).
5. If the broker uses suffixed symbols (e.g. `EURUSD.pro`), note them — pass
   `--mt5-symbol-map EURUSD=EURUSD.pro` (repeatable) to the commands below.

## 2. Verify the install (no orders)

```powershell
quanthack check-environment
quanthack preflight
python -m unittest discover -s tests   # expect OK (554 tests)
```

## 3. Pre-go-live validation sequence — DO THIS IN ORDER

1. **Read-only connection probe** (confirms login + data, places nothing):
   ```powershell
   quanthack mt5-probe --confirm-read-only-mt5
   ```
2. **Shadow run** (computes & journals intended orders, sends NOTHING):
   ```powershell
   .\run_shadow.bat
   ```
   Watch `outputs\live_orders_journal.jsonl` — every line should be
   `MT5_SHADOW` with a sensible `note` ("would BUY 0.10 lots ..."). Sanity-check
   the symbols, directions, and lot sizes.
3. **One tiny manual order** (independent path, proves order_send works on your
   broker). Get a price from the probe, then:
   ```powershell
   quanthack manual-ticket --symbol EURUSD --side BUY --target-notional 5000 --price <ask>
   ```
   …and place that small order once in MT5 to confirm the account accepts it.
4. **Go live small.** Edit `run_live.bat` to a tiny `--max-order-lots` (e.g.
   0.05), then:
   ```powershell
   .\run_live.bat
   ```
   Journal lines become `MT5_FILLED`. Confirm the position appears in MT5. Only
   then raise `--max-order-lots`.

## 4. How the safety gates work

| Gate | Effect |
|---|---|
| no `--i-understand-live-orders` | **shadow mode** — never calls `order_send` |
| `--adapter mt5` required | live-trade only runs against MT5 |
| RiskEngine (in the loop) | blocked decisions never reach the executor |
| `--max-order-lots` | hard cap on any single order |
| position reconciliation | a repeated target sends the *delta*, not a stacked duplicate |
| resilient loop | a transient tick error is logged & skipped, the bot keeps running (avoids the >8h inactivity elimination) |
| auto-reconnect | after a failed tick the loop closes + re-initializes the MT5 connection, so a dropped link self-heals instead of idling the bot |
| kill-switch | `quanthack mt5-flatten` / `run_flatten.bat` closes ALL positions instantly (emergency de-risk or end-of-round protection) |

## 4a. Kill-switch (flatten everything)

If the bot misbehaves, the market gaps, or you want to lock a round's result
before the 22:00 cut, flatten all positions in one command:

```powershell
quanthack mt5-flatten --config configs\competition.toml                       # SHADOW: reports only
quanthack mt5-flatten --config configs\competition.toml --i-understand-live-orders   # LIVE: closes all
```

or double-click `run_flatten.bat`. Keep this window handy during live trading.

## 5. Recommended live command (after validation)

```powershell
quanthack live-trade --config configs\competition.toml --adapter mt5 ^
  --poll-seconds 60 --iterations 100000 --max-order-lots 0.10 ^
  --max-live-positions 2 --reduce-only-daily-loss-pct 0.0012 ^
  --reduce-only-rolling-sharpe -2.0 --live-metrics-csv outputs\live_metrics.csv ^
  --sentiment-snapshot outputs\fx_sentiment_snapshot.json ^
  --sentiment-conflict-threshold 1.25 ^
  --symbol-state-snapshot outputs\live_deal_attribution_latest.json ^
  --blocked-symbol-state cooldown_realized_drag ^
  --strategy opportunity_probe ^
  --symbol AUDUSD --symbol EURGBP --symbol EURUSD --symbol GBPUSD ^
  --symbol USDCAD --symbol USDCHF --symbol USDJPY ^
  --i-understand-live-orders
```

Keep the MT5 terminal open and the PC awake (disable sleep) for the whole round.
`--iterations 100000 --poll-seconds 60` ≈ runs continuously; the loop self-heals
on transient errors but **monitor it** — restart the .bat if the machine reboots.

## 6. Hard limits to respect (from the rules)
- **Log in within 8h of the 22:00 launch** or you're eliminated — start tonight.
- Forced liquidation (30% margin level) = elimination. The competition-safe
  config keeps leverage ~5x and margin level far above that; do not crank
  `--max-order-lots` so high that gross leverage approaches the 28x discipline
  line.
- API: stay well under 500 requests/sec. `--poll-seconds 60` is far below that.

## 7. Known limitations / what to watch
- `order_send` filling mode is `IOC`; if your broker rejects it, switch to
  `ORDER_FILLING_FOK`/`RETURN` in `src/quanthack/trading/mt5_executor.py`
  (`type_filling`). The journal `note` shows the broker `retcode`/`comment` on
  failure — check it after the first live order.
- Non-USD-quote crosses (EURGBP, EURCHF) need a quote→USD rate; the executor
  fetches `GBPUSD`/`CHFUSD` ticks automatically — make sure those symbols exist
  on your broker (add to the symbol map if suffixed).
- Contract sizes come from MT5 `symbol_info`; metals/crypto vary by broker —
  verify the shadow-mode lot sizes look right before going live.
