from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


OUT = Path("outputs/fx_sentiment_snapshot.json")
HISTORY = Path("outputs/fx_sentiment_history.jsonl")

QUERIES = {
    "USD": "US dollar Federal Reserve Treasury yields inflation forex",
    "EUR": "euro ECB inflation growth forex",
    "GBP": "pound sterling Bank of England inflation wages forex",
    "JPY": "Japanese yen Bank of Japan yields forex",
    "CAD": "Canadian dollar Bank of Canada oil forex",
    "CHF": "Swiss franc SNB safe haven forex",
    "AUD": "Australian dollar RBA China commodities forex",
}

PAIRS = ("AUDUSD", "EURGBP", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY")

POSITIVE_WORDS = {
    "gain",
    "gains",
    "higher",
    "rises",
    "rise",
    "strong",
    "stronger",
    "hawkish",
    "hike",
    "hikes",
    "inflation",
    "yield",
    "yields",
    "resilient",
    "beats",
}
NEGATIVE_WORDS = {
    "fall",
    "falls",
    "lower",
    "weak",
    "weaker",
    "dovish",
    "cut",
    "cuts",
    "recession",
    "misses",
    "slows",
    "slump",
    "pressure",
}


def main() -> None:
    currencies: dict[str, dict] = {}
    for currency, query in QUERIES.items():
        headlines = _fetch_headlines(query)
        score = _score_headlines(headlines)
        currencies[currency] = {
            "score": score,
            "label": _label(score),
            "query": query,
            "headlines": headlines,
        }

    pairs = {}
    for pair in PAIRS:
        base, quote = pair[:3], pair[3:]
        pair_score = currencies.get(base, {}).get("score", 0.0) - currencies.get(
            quote, {}
        ).get("score", 0.0)
        pairs[pair] = {"score": pair_score, "label": _label(pair_score)}

    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": (
            "Google News RSS headline keyword score. Use as context only; "
            "technical/risk gates remain primary."
        ),
        "currencies": currencies,
        "pairs": pairs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "timestamp_utc": snapshot["timestamp_utc"],
                "pairs": pairs,
            },
            sort_keys=True,
        )
    )


def _fetch_headlines(query: str, limit: int = 8) -> list[dict[str, str]]:
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode(
            {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 quanthack-live-monitor/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read()
    except OSError as exc:
        return [{"title": f"fetch_error: {exc}", "link": "", "published": ""}]

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [{"title": f"parse_error: {exc}", "link": "", "published": ""}]

    headlines: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:limit]:
        headlines.append(
            {
                "title": _text(item.find("title")),
                "link": _text(item.find("link")),
                "published": _text(item.find("pubDate")),
                "source": _text(item.find("source")),
            }
        )
    return headlines


def _score_headlines(headlines: list[dict[str, str]]) -> float:
    score = 0.0
    counted = 0
    for item in headlines:
        title = item.get("title", "").lower()
        if title.startswith(("fetch_error", "parse_error")):
            continue
        words = {
            "".join(ch for ch in raw if ch.isalnum())
            for raw in title.replace("-", " ").split()
        }
        score += len(words & POSITIVE_WORDS)
        score -= len(words & NEGATIVE_WORDS)
        counted += 1
    if counted == 0:
        return 0.0
    return max(min(score / counted, 3.0), -3.0)


def _label(score: float) -> str:
    if score >= 0.35:
        return "supportive"
    if score <= -0.35:
        return "negative"
    return "neutral"


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


if __name__ == "__main__":
    main()
