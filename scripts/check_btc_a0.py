#!/usr/bin/env python3
"""Static contract checks for the BTCUSDC A0 equity page."""

from __future__ import annotations

import json
import math
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "btc-a0.html"
DATA = ROOT / "data" / "btc-a0-equity.json"
INDEX = ROOT / "index.html"
LINKS = ROOT / "data" / "links.json"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        for key in ("href", "src"):
            if values.get(key):
                self.references.add(values[key] or "")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    check(parsed.tzinfo is not None, f"timestamp must include timezone: {value}")
    return parsed


def main() -> None:
    parser = PageParser()
    page_text = PAGE.read_text(encoding="utf-8")
    parser.feed(page_text)
    required_ids = {
        "net-profit", "return-pct", "current-status", "updated-at",
        "equity-chart", "chart-tooltip", "tooltip-time", "tooltip-profit",
        "tooltip-return", "data-warning",
    }
    check(required_ids <= parser.ids, f"missing page ids: {sorted(required_ids - parser.ids)}")
    check("assets/styles.css" in parser.references, "shared stylesheet is not referenced")
    check("data/btc-a0-equity.json" in page_text, "equity data file is not fetched")
    check("userTrades" in page_text, "userTrades accounting note is missing")
    check("观察中" in page_text, "watching state is missing")

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    check(payload.get("schema_version") == 1, "unsupported schema_version")
    check(payload.get("symbol") == "BTCUSDC", "symbol must be BTCUSDC")
    check(payload.get("strategy") == "A0", "strategy must be A0")
    check(payload.get("mode") in {"placeholder", "live"}, "invalid mode")
    check(payload.get("status") == "watching", "initial status must be watching")
    initial_equity = payload.get("initial_equity")
    check(isinstance(initial_equity, (int, float)) and initial_equity > 0, "initial_equity must be positive")
    check(parse_time(payload["updated_at"]) is not None, "invalid updated_at")

    points = payload.get("points")
    check(isinstance(points, list) and len(points) >= 3, "at least three chart points are required")
    times: list[datetime] = []
    profits: list[float] = []
    for index, point in enumerate(points):
        check(isinstance(point, dict), f"point {index} must be an object")
        times.append(parse_time(point["time"]))
        profit = point.get("profit")
        return_pct = point.get("return_pct")
        check(isinstance(profit, (int, float)) and math.isfinite(profit), f"point {index} has invalid profit")
        check(isinstance(return_pct, (int, float)) and math.isfinite(return_pct), f"point {index} has invalid return_pct")
        expected = profit / initial_equity * 100
        check(math.isclose(return_pct, expected, abs_tol=0.0001), f"point {index} return_pct is inconsistent")
        profits.append(float(profit))
    check(times == sorted(times) and len(set(times)) == len(times), "point times must be unique and ascending")
    check(min(profits) < 0 < max(profits), "placeholder chart must demonstrate up/down movement")
    if payload["mode"] == "placeholder":
        check(payload.get("summary") == {"net_profit": None, "return_pct": None}, "placeholder summary must not claim live returns")

    index_text = INDEX.read_text(encoding="utf-8")
    check('href="./btc-a0.html"' in index_text, "homepage card is missing")
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    matches = [item for item in links if item.get("url") == "./btc-a0.html"]
    check(len(matches) == 1, "links.json must contain exactly one BTC A0 entry")
    check(matches[0].get("name") == "BTCUSDC A0 收益曲线", "links.json BTC A0 name mismatch")

    print(f"PASS HTML: {PAGE.relative_to(ROOT)} ({len(parser.ids)} ids)")
    print(f"PASS DATA: {DATA.relative_to(ROOT)} ({len(points)} points, ascending timestamps, signed movement)")
    print("PASS LINKS: homepage card and data/links.json entry are consistent")


if __name__ == "__main__":
    main()
