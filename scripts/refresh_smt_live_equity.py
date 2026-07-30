#!/usr/bin/env python3
"""Generate public equity and update GitHub only when semantic live data changes."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/opt/smt-live-equity")
SESSION = Path("/opt/freqtrade-lab/user_data/research/smt_top12_short_ft_20260627/real_signal_strategy_exit_gtx_v2_btcusdc_A_adverse_burst_retrace/sessions/A0_20260730T032031Z")
JSONL = SESSION / "phase_b_v2_20260730T032031Z.jsonl"
HEARTBEAT = SESSION / "heartbeat.json"
OUTPUT = ROOT / "btc-a0-equity.json"
STATE = ROOT / "published.json"
API = "https://api.github.com/repos/Yiyoki/kiki-nav/contents/data/btc-a0-equity.json"


def token() -> str:
    # Credentials remain in private files; never log their contents.
    dedicated = ROOT / "github.token"
    try:
        value = dedicated.read_text(encoding="utf-8").strip()
        if value:
            return value
    except (OSError, UnicodeError):
        pass
    for filename in (Path("/opt/keys.md"), Path("/opt/key.txt")):
        try:
            text = filename.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        candidates = re.findall(r"(?:github[^\n:=]*[=:]\s*|\b)(gh[ps]_[A-Za-z0-9_]{20,})", text, re.I)
        if candidates:
            return candidates[0] if isinstance(candidates[0], str) else candidates[0][-1]
    raise RuntimeError("GitHub token unavailable in private credential files")


def request(method: str, auth: str, payload=None):
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {auth}", "User-Agent": "smt-live-equity-refresh", "X-GitHub-Api-Version": "2022-11-28"}
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def semantic(value):
    copy = dict(value)
    copy.pop("generated_at", None)
    return copy


def main() -> int:
    subprocess.run([str(ROOT / "build_smt_live_equity.py"), str(JSONL), "--heartbeat", str(HEARTBEAT), "--output", str(OUTPUT)], check=True)
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if STATE.exists() and semantic(json.loads(STATE.read_text(encoding="utf-8"))) == semantic(current):
        return 0
    auth = token()
    remote = request("GET", auth)
    remote_value = json.loads(base64.b64decode(remote["content"]))
    if semantic(remote_value) == semantic(current):
        STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    result = request("PUT", auth, {
        "message": f"Update SMT live equity ({current['status']}, {len(current['points'])} points)",
        "content": base64.b64encode(OUTPUT.read_bytes()).decode(),
        "sha": remote["sha"],
        "branch": "main",
    })
    STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result["commit"]["sha"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"smt-live-equity refresh failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
