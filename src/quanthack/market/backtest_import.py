from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc


PRICE_FIELDS = ("timestamp", "symbol", "close")
QUOTE_FIELDS = ("timestamp", "symbol", "bid", "ask")
PRICER_REQUIRED_COLUMNS = ("time", "sym", "bid", "ask")


@dataclass(frozen=True)
class ImportedBacktestDataSummary:
    input_path: str
    price_csv: str
    quote_csv: str
    symbols: tuple[str, ...]
    files_seen: int
    files_imported: int
    ticks_seen: int
    bars_written: int
    bar_seconds: int


def import_pricer_zip_to_backtest_csv(
    *,
    input_path: str | Path,
    price_output: str | Path,
    quote_output: str | Path,
    symbols: tuple[str, ...],
    bar_seconds: int = 900,
    source_timezone: str = "UTC",
    max_files_per_symbol: int | None = None,
    progress_every_files: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> ImportedBacktestDataSummary:
    """Convert a pricer zip archive or extracted pricer-output directory to CSV bars."""
    if not symbols:
        raise ValueError("at least one symbol is required")
    if bar_seconds < 1:
        raise ValueError("bar_seconds must be at least 1")
    if max_files_per_symbol is not None and max_files_per_symbol < 1:
        raise ValueError("max_files_per_symbol must be at least 1 when provided")
    if progress_every_files is not None and progress_every_files < 1:
        raise ValueError("progress_every_files must be at least 1 when provided")

    input_file = Path(input_path).expanduser()
    if not input_file.exists():
        raise FileNotFoundError(f"backtest data archive not found: {input_file}")
    if input_file.is_file() and input_file.stat().st_size == 0:
        raise ValueError(f"backtest data archive is empty: {input_file}")

    selected_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols)
    selected_set = set(selected_symbols)
    timezone = ZoneInfo(source_timezone)
    bars: dict[tuple[str, datetime], tuple[float, float]] = {}
    ticks_seen = 0
    files_seen = 0
    files_imported = 0
    imported_by_symbol = {symbol: 0 for symbol in selected_symbols}

    try:
        if input_file.is_dir():
            paths = tuple(
                sorted(path for path in input_file.glob("*.parquet") if path.is_file())
            )
            files_seen = len(paths)
            _emit_progress(
                progress_callback,
                f"directory contains {files_seen} parquet files",
            )
            for path in paths:
                symbol = _symbol_from_pricer_name(path.name)
                if symbol not in selected_set:
                    continue
                if (
                    max_files_per_symbol is not None
                    and imported_by_symbol[symbol] >= max_files_per_symbol
                ):
                    continue
                with path.open("rb") as handle:
                    rows = _read_pricer_rows(handle)
                imported_by_symbol[symbol] += 1
                files_imported += 1
                for row in rows:
                    timestamp = _parse_pricer_time(str(row["time"]), timezone)
                    if row["bid"] is None or row["ask"] is None:
                        continue
                    bid = float(row["bid"])
                    ask = float(row["ask"])
                    if bid <= 0 or ask <= 0 or ask < bid:
                        continue
                    row_symbol = _normalize_symbol(str(row.get("sym") or symbol))
                    if row_symbol not in selected_set:
                        continue
                    bucket = _floor_timestamp(timestamp, bar_seconds)
                    bars[(row_symbol, bucket)] = (bid, ask)
                    ticks_seen += 1
                if (
                    progress_callback is not None
                    and progress_every_files is not None
                    and files_imported % progress_every_files == 0
                ):
                    _emit_progress(
                        progress_callback,
                        (
                            f"imported {files_imported} files, "
                            f"read {ticks_seen:,} ticks, "
                            f"built {len(bars):,} bars"
                        ),
                    )
        else:
            with ZipFile(input_file) as archive:
                names = tuple(
                    name for name in archive.namelist() if name.endswith(".parquet")
                )
                files_seen = len(names)
                _emit_progress(
                    progress_callback,
                    f"archive contains {files_seen} parquet files",
                )
                for name in names:
                    symbol = _symbol_from_pricer_name(name)
                    if symbol not in selected_set:
                        continue
                    if (
                        max_files_per_symbol is not None
                        and imported_by_symbol[symbol] >= max_files_per_symbol
                    ):
                        continue
                    with archive.open(name) as handle:
                        rows = _read_pricer_rows(handle)
                    imported_by_symbol[symbol] += 1
                    files_imported += 1
                    for row in rows:
                        timestamp = _parse_pricer_time(str(row["time"]), timezone)
                        if row["bid"] is None or row["ask"] is None:
                            continue
                        bid = float(row["bid"])
                        ask = float(row["ask"])
                        if bid <= 0 or ask <= 0 or ask < bid:
                            continue
                        row_symbol = _normalize_symbol(str(row.get("sym") or symbol))
                        if row_symbol not in selected_set:
                            continue
                        bucket = _floor_timestamp(timestamp, bar_seconds)
                        bars[(row_symbol, bucket)] = (bid, ask)
                        ticks_seen += 1
                    if (
                        progress_callback is not None
                        and progress_every_files is not None
                        and files_imported % progress_every_files == 0
                    ):
                        _emit_progress(
                            progress_callback,
                            (
                                f"imported {files_imported} files, "
                                f"read {ticks_seen:,} ticks, "
                                f"built {len(bars):,} bars"
                            ),
                        )
    except BadZipFile as exc:
        raise ValueError(
            f"{input_file} is not a complete readable zip archive. "
            "If this came from Downloads, wait until the .zip.part file finishes."
        ) from exc

    if not bars:
        raise ValueError(
            f"no usable ticks found for {', '.join(selected_symbols)} in {input_file}"
        )

    _emit_progress(
        progress_callback,
        (
            f"writing {len(bars):,} bars from {files_imported} imported files "
            f"to {price_output} and {quote_output}"
        ),
    )

    price_path = Path(price_output)
    quote_path = Path(quote_output)
    price_path.parent.mkdir(parents=True, exist_ok=True)
    quote_path.parent.mkdir(parents=True, exist_ok=True)

    ordered = sorted(bars.items(), key=lambda item: (item[0][0], item[0][1]))
    with price_path.open("w", encoding="utf-8", newline="") as price_handle:
        price_writer = csv.DictWriter(price_handle, fieldnames=PRICE_FIELDS)
        price_writer.writeheader()
        for (symbol, timestamp), (bid, ask) in ordered:
            price_writer.writerow(
                {
                    "timestamp": timestamp.isoformat(timespec="seconds"),
                    "symbol": symbol,
                    "close": f"{((bid + ask) / 2):.10f}",
                }
            )

    with quote_path.open("w", encoding="utf-8", newline="") as quote_handle:
        quote_writer = csv.DictWriter(quote_handle, fieldnames=QUOTE_FIELDS)
        quote_writer.writeheader()
        for (symbol, timestamp), (bid, ask) in ordered:
            quote_writer.writerow(
                {
                    "timestamp": timestamp.isoformat(timespec="seconds"),
                    "symbol": symbol,
                    "bid": f"{bid:.10f}",
                    "ask": f"{ask:.10f}",
                }
            )

    written_symbols = tuple(sorted({symbol for (symbol, _), _ in ordered}))
    _emit_progress(
        progress_callback,
        (
            f"finished import: {len(ordered):,} bars for "
            f"{', '.join(written_symbols)}"
        ),
    )
    return ImportedBacktestDataSummary(
        input_path=str(input_file),
        price_csv=str(price_path),
        quote_csv=str(quote_path),
        symbols=written_symbols,
        files_seen=files_seen,
        files_imported=files_imported,
        ticks_seen=ticks_seen,
        bars_written=len(ordered),
        bar_seconds=bar_seconds,
    )


def _emit_progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _read_pricer_rows(handle) -> list[dict]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow is required to import downloaded Parquet backtest data. "
            "Install it with: python -m pip install pyarrow"
        ) from exc

    table = pq.read_table(handle, columns=list(PRICER_REQUIRED_COLUMNS))
    return table.to_pylist()


def _symbol_from_pricer_name(name: str) -> str:
    filename = Path(name).name
    return _normalize_symbol(filename.split("_", 1)[0])


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _parse_pricer_time(value: str, source_timezone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone)
    return parsed.astimezone(UTC)


def _floor_timestamp(timestamp: datetime, bar_seconds: int) -> datetime:
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp((epoch // bar_seconds) * bar_seconds, tz=UTC)
