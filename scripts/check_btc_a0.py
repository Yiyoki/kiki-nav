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
    check("SMT小额实盘" in page_text, "page title is missing")
    check("window.setInterval(refreshData, 60_000)" in page_text, "60-second polling is missing")
    check("clean.unshift({ time: start, profit: 0, return_pct: 0 })" in page_text, "frontend zero-point prepend is missing")

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    check(payload.get("schema_version") in {1, 2}, "unsupported schema_version")
    check(payload.get("mode") == "live", "mode must be live")
    check(payload.get("status") in {"running", "stopped"}, "invalid live status")
    initial_equity = payload.get("base_capital")
    check(math.isclose(initial_equity, 99.49405209), "base_capital mismatch")
    check(parse_time(payload["generated_at"]) is not None, "invalid generated_at")
    check(parse_time(payload["session_start"]) is not None, "invalid session_start")
    check(payload.get("accounting_scope") in {"complete", "partial"}, "invalid accounting scope")

    points = payload.get("points")
    check(isinstance(points, list) and len(points) >= 1, "at least one chart point is required")
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
    check(points[0]["time"] == payload["session_start"], "first point must be session_start")
    check(points[0]["profit"] == 0 and points[0]["return_pct"] == 0, "first point must be 0/0%")
    if payload.get("schema_version") == 1:
        check(payload.get("summary") == {"net_profit": points[-1]["profit"], "return_pct": points[-1]["return_pct"]}, "summary must equal last point")
    else:
        summary = payload.get("summary", {})
        for key in ("realized_net", "unrealized_mtm", "strategy_mtm"):
            check(isinstance(summary.get(key), (int, float)) and math.isfinite(summary[key]), f"summary missing {key}")
        check(math.isclose(summary["net_profit"], summary["realized_net"], abs_tol=1e-8), "net_profit must equal realized_net")
        check(math.isclose(summary["strategy_mtm"], summary["realized_net"] + summary["unrealized_mtm"], abs_tol=1e-8), "strategy_mtm formula mismatch")

    index_text = INDEX.read_text(encoding="utf-8")
    check('href="./btc-a0.html"' in index_text, "homepage card is missing")
    links = json.loads(LINKS.read_text(encoding="utf-8"))
    matches = [item for item in links if item.get("url") == "./btc-a0.html"]
    check(len(matches) == 1, "links.json must contain exactly one BTC A0 entry")
    check(matches[0].get("name") == "SMT小额实盘", "links.json title mismatch")
    check("SMT小额实盘" in index_text, "homepage title mismatch")

    print(f"PASS HTML: {PAGE.relative_to(ROOT)} ({len(parser.ids)} ids)")
    print(f"PASS DATA: {DATA.relative_to(ROOT)} ({len(points)} points, live schema and zero origin)")
    print("PASS LINKS: homepage card and data/links.json entry are consistent")


if __name__ == "__main__":
    main()
