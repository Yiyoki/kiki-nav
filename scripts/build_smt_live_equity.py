#!/usr/bin/env python3
"""Build a public, de-identified SMT live realized-equity JSON from session JSONL."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

BASE_CAPITAL = Decimal("99.49405209")
ZERO = Decimal("0")
END_TYPES = {"session_end", "session_stop", "session_stopped", "session_complete", "session_completed"}


def iso_time(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, timezone.utc).isoformat()
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        return ZERO
    return result if result.is_finite() else ZERO


def event_time(value: dict[str, Any], fallback: str | None = None) -> str | None:
    for key in ("time", "ts", "timestamp", "tradeTime", "T", "updateTime", "transactTime"):
        parsed = iso_time(value.get(key))
        if parsed:
            return parsed
    return fallback


def trade_groups(value: Any, inherited_time: str | None = None) -> Iterable[tuple[dict[str, Any], str | None]]:
    """Find userTrades payloads regardless of their wrapper/event layout."""
    if isinstance(value, dict):
        current_time = event_time(value, inherited_time)
        for key, child in value.items():
            if key in {"userTrades", "user_trades"}:
                items = child if isinstance(child, list) else [child]
                for item in items:
                    if isinstance(item, dict):
                        yield item, event_time(item, current_time)
            elif isinstance(child, (dict, list)):
                yield from trade_groups(child, current_time)
    elif isinstance(value, list):
        for child in value:
            yield from trade_groups(child, inherited_time)


def dedup_key(trade: dict[str, Any]) -> str:
    trade_id = next((trade.get(k) for k in ("tradeId", "trade_id", "id") if trade.get(k) is not None), None)
    order_id = next((trade.get(k) for k in ("orderId", "order_id") if trade.get(k) is not None), None)
    if trade_id is not None:
        return f"trade:{trade_id}"
    if order_id is not None:
        # One order can have multiple fills; include fill time and amount fields where available.
        parts = [order_id, trade.get("time"), trade.get("tradeTime"), trade.get("realizedPnl"), trade.get("commission")]
        return "order:" + hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()
    clean = {k: v for k, v in trade.items() if k not in {"event_id", "request_id"}}
    return "anon:" + hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()


def build(jsonl: Path, heartbeat: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for raw in jsonl.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue  # tolerate a partially written last line
        if isinstance(value, dict):
            events.append(value)
    starts = [event_time(e) for e in events if str(e.get("type", e.get("event_type", ""))).lower() == "session_start"]
    session_start = next((x for x in starts if x), None) or (event_time(events[0]) if events else None)
    if not session_start:
        raise ValueError("JSONL contains no usable session_start timestamp")

    stopped = any(str(e.get("type", e.get("event_type", ""))).lower() in END_TYPES for e in events)
    if heartbeat and heartbeat.exists():
        try:
            hb = json.loads(heartbeat.read_text(encoding="utf-8"))
            stopped = stopped or str(hb.get("status", hb.get("state", ""))).lower() in {"stopped", "complete", "completed", "ended"}
            end_at = iso_time(hb.get("end_at_utc") or hb.get("ended_at"))
            if end_at and datetime.fromisoformat(end_at.replace("Z", "+00:00")) <= (now or datetime.now(timezone.utc)):
                stopped = True
        except (json.JSONDecodeError, OSError):
            pass

    seen: set[str] = set()
    trades: list[tuple[str, Decimal, bool]] = []
    partial = False
    for event in events:
        for trade, inherited_time in trade_groups(event):
            key = dedup_key(trade)
            if key in seen:
                continue
            seen.add(key)
            when = event_time(trade, inherited_time)
            if not when:
                continue
            pnl = decimal(trade.get("realizedPnl", trade.get("realized_pnl")))
            commission = decimal(trade.get("commission"))
            asset = str(trade.get("commissionAsset", trade.get("commission_asset", ""))).upper()
            reliable = commission == ZERO or asset == "USDC"
            net = pnl - commission if reliable else pnl
            partial = partial or not reliable
            trades.append((when, net, reliable))

    trades.sort(key=lambda row: row[0])
    cumulative = ZERO
    points = [{"time": session_start, "profit": 0.0, "return_pct": 0.0}]
    for when, net, _ in trades:
        cumulative += net
        points.append({
            "time": when,
            "profit": float(round(cumulative, 8)),
            "return_pct": float(round(cumulative / BASE_CAPITAL * 100, 8)),
        })
    generated_dt = now or datetime.now(timezone.utc)
    generated = generated_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    # Keep a liveness point even without trades so the public chart's x-axis
    # advances and visibly proves the monitor is still running.
    if points[-1]["time"] != generated:
        points.append({
            "time": generated,
            "profit": float(round(cumulative, 8)),
            "return_pct": float(round(cumulative / BASE_CAPITAL * 100, 8)),
        })
    scope = "partial" if partial else "complete"
    status = "stopped" if stopped else "running"
    return {
        "schema_version": 1,
        "mode": "live",
        "status": status,
        "status_label": "已停止" if stopped else "运行中",
        "accounting_scope": scope,
        "accounting_note": ("净已实现收益；非 USDC 手续费未换算、未扣除" if partial else "净已实现收益（realizedPnl 减 USDC 手续费）"),
        "base_capital": float(BASE_CAPITAL),
        "generated_at": generated,
        "session_start": session_start,
        "summary": {"net_profit": float(round(cumulative, 8)), "return_pct": float(round(cumulative / BASE_CAPITAL * 100, 8))},
        "points": points[-288:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--heartbeat", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build(args.jsonl, args.heartbeat)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
