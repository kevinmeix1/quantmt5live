# Manual MT5 Desktop Execution

Use this path only when the official MT5 Python bridge is unavailable on macOS.
The Python project still does research, risk checks, and ticket sizing. You enter
the order by hand in MT5 desktop.

## Workflow

1. Use the strategy/backtest tools to choose a conservative candidate trade.
2. Read the current MT5 bid/ask from the desktop terminal.
3. Build a manual ticket in VS Code.
4. If the ticket says `BLOCKED`, do not trade.
5. If the ticket says `APPROVED`, enter the exact rounded MT5 volume by hand.
6. Confirm the position appears in MT5.
7. Record a note or dry-run journal entry so the local project stays auditable.

## Build A Ticket

For a BUY, use the MT5 ask price. For a SELL, use the MT5 bid price.

```bash
quanthack manual-ticket \
  --symbol EURUSD \
  --side BUY \
  --target-notional 50000 \
  --price 1.1002
```

The output gives:

- risk decision;
- broker symbol;
- order side;
- risk-adjusted notional;
- rounded MT5 lots;
- exact MT5 desktop steps.

## MT5 Desktop Steps

1. Open Market Watch.
2. Find the broker symbol, for example `EURUSD`.
3. Right-click the symbol and inspect `Specification`.
4. Confirm contract size, minimum volume, and volume step.
5. Click `New Order`.
6. Set type to market execution.
7. Enter the ticket's rounded volume.
8. Click BUY or SELL.
9. Check the Trade tab to confirm the position.

## Important Sizing Notes

MT5 uses volume in lots. Our project thinks in USD notional.

For common FX pairs:

- `EURUSD`, `GBPUSD`, `AUDUSD`: USD notional changes with price.
- `USDJPY`, `USDCAD`, `USDCHF`: one standard lot is usually about `100,000`
  USD notional.

For metals and crypto, always pass contract size from MT5 Symbol Specification:

```bash
quanthack manual-ticket \
  --symbol XAUUSD \
  --side BUY \
  --target-notional 50000 \
  --price 2300 \
  --contract-size 100
```

For broker suffixes:

```bash
quanthack manual-ticket \
  --symbol EURUSD \
  --broker-symbol EURUSD.pro \
  --side BUY \
  --price 1.1002
```

## Safety Rule

Manual execution is allowed only as an operational workaround. Do not increase
size to compensate for slowness. If the setup is unclear, skip the trade.
