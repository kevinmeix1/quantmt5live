# Market Data Validation

Step 23 adds a market data validation command.

Backtests are only useful when the price and quote data are coherent. A strategy
can look better or worse simply because rows are missing, duplicated, or badly
aligned.

## New Command

```bash
python scripts/evaluation/validate_market_data.py
```

By default this validates the configured backtest CSVs for the active strategy
symbol.

It writes:

```text
outputs/backtests/data_health.csv
```

## What It Checks

For each selected symbol:

- Price row count.
- Quote row count.
- Price and quote time ranges.
- Duplicate price timestamps.
- Duplicate quote timestamps.
- Price bars missing matching quotes.
- Quotes without matching price bars.
- Maximum price gap.
- Maximum quote gap.
- Maximum quote spread.

## Status Levels

```text
OK    - data looks aligned for the selected symbol
WARN  - data is usable but deserves attention
FAIL  - data should not be trusted for backtesting
```

Examples:

- Missing quote for a price bar: `FAIL`
- Duplicate timestamp: `FAIL`
- Extra quote without a price bar: `WARN`
- Large time gap: `WARN`
- Spread above the market-quality limit: `WARN`

## Run In VS Code Terminal

Validate the configured backtest data:

```bash
python scripts/evaluation/validate_market_data.py
```

Validate all symbols in the files:

```bash
python scripts/evaluation/validate_market_data.py --all-symbols
```

Validate all 15 configured competition instruments:

```bash
python scripts/evaluation/validate_market_data.py --competition-symbols
```

Use this stricter mode after importing MT5 or organizer data. It will fail if
crypto symbols such as `BTCUSD`, `ETHUSD`, `SOLUSD`, `XRPUSD`, or `BARUSD` are
missing.

Validate a specific symbol:

```bash
python scripts/evaluation/validate_market_data.py --symbol EURUSD
```

Change the gap warning threshold:

```bash
python scripts/evaluation/validate_market_data.py --max-gap-seconds 600
```

## Why This Matters

The project now has backtesting, sweep, and a research report. This validation
step makes sure those outputs are not quietly based on broken CSV alignment.

This is still offline and dry-run only. It does not call a broker or any live
market data API.
