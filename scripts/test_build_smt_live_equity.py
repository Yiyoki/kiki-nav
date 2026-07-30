#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from build_smt_live_equity import BASE_CAPITAL, build


class BuilderTest(unittest.TestCase):
    def make(self, events, heartbeat=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        source = root / "events.jsonl"
        source.write_text("\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8")
        hb = root / "heartbeat.json"
        if heartbeat is not None:
            hb.write_text(json.dumps(heartbeat), encoding="utf-8")
        return build(source, hb if heartbeat is not None else None, datetime(2026, 7, 30, 4, tzinfo=timezone.utc))

    def test_current_no_trade_session_is_live_running_zero(self):
        payload = self.make([{"type": "session_start", "ts": "2026-07-30T03:20:34.803042Z"}])
        self.assertEqual(payload["mode"], "live")
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["accounting_scope"], "complete")
        self.assertEqual(payload["points"][0], {"time": "2026-07-30T03:20:34.803042Z", "profit": 0.0, "return_pct": 0.0})
        self.assertEqual(payload["points"][-1]["time"], "2026-07-30T04:00:00Z")
        self.assertEqual(payload["points"][-1]["profit"], 0.0)
        self.assertEqual(payload["summary"], {"net_profit": 0.0, "return_pct": 0.0})

    def test_historical_wrappers_dedup_and_commission_scope(self):
        events = [
            {"type": "session_start", "ts": "2026-07-30T03:20:00Z"},
            {"type": "sync", "ts": "2026-07-30T03:30:00Z", "response": {"userTrades": [
                {"tradeId": 7, "orderId": 70, "time": 1785382200000, "realizedPnl": "2.5", "commission": "0.1", "commissionAsset": "USDC"},
                {"tradeId": 8, "orderId": 80, "time": 1785382260000, "realizedPnl": "1", "commission": "0.01", "commissionAsset": "BNB"},
            ]}},
            {"type": "poll", "userTrades": {"tradeId": 7, "orderId": 70, "time": 1785382200000, "realizedPnl": "2.5", "commission": "0.1", "commissionAsset": "USDC"}},
        ]
        payload = self.make(events)
        self.assertEqual(payload["accounting_scope"], "partial")
        self.assertEqual(len(payload["points"]), 4)
        self.assertAlmostEqual(payload["summary"]["net_profit"], 3.4)
        self.assertAlmostEqual(payload["summary"]["return_pct"], float(round(3.4 / float(BASE_CAPITAL) * 100, 8)))
        serialized = json.dumps(payload)
        self.assertNotIn("tradeId", serialized)
        self.assertNotIn("orderId", serialized)

    def test_end_event_and_heartbeat_deadline_stop(self):
        payload = self.make([
            {"type": "session_start", "ts": "2026-07-30T03:20:00Z"},
            {"type": "session_end", "ts": "2026-07-30T03:50:00Z"},
        ])
        self.assertEqual(payload["status"], "stopped")
        deadline = self.make([{"type": "session_start", "ts": "2026-07-30T03:20:00Z"}], {"end_at_utc": "2026-07-30T03:59:00Z"})
        self.assertEqual(deadline["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
