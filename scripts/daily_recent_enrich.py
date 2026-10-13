#!/usr/bin/env python3
"""
Daily incremental recent-activity enrichment for x-following-audit.

Safe defaults: small batch, per-account checkpoint, stop on rate limit.
Read-only with respect to X (no unfollows).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data" / "following_audit"
LOG_DIR = AUDIT_DIR / "logs"
STATE_PATH = AUDIT_DIR / "daily_enrich_state.json"

sys.path.insert(0, str(ROOT / "scripts"))
import following_recent_audit as fra  # noqa: E402


def log(msg: str, log_path: Path) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_recent_audit() -> Path | None:
    candidates = sorted(
        AUDIT_DIR.glob("following_audit_*_recent.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def latest_static_audit() -> Path | None:
    candidates = [
        p
        for p in sorted(AUDIT_DIR.glob("following_audit_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not p.name.endswith("_recent.json")
    ]
    return candidates[0] if candidates else None


def resolve_audit_path(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    recent = latest_recent_audit()
    if recent:
        return recent
    static = latest_static_audit()
    if not static:
        raise SystemExit("No following_audit_*.json found under data/following_audit")
    out = static.with_name(static.stem + "_recent.json")
    out.write_text(static.read_text(encoding="utf-8"), encoding="utf-8")
    return out


def daily_enriched_today(state: dict[str, Any]) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_run_date") != today:
        return 0
    return int(state.get("enriched_today") or 0)


def should_skip(state: dict[str, Any], daily_cap: int, force: bool) -> bool:
    if force:
        return False
    return daily_enriched_today(state) >= daily_cap


def enrich_batch(
    path: Path,
    *,
    batch_size: int,
    sleep_s: float,
    tweet_count: int,
    timeout_s: int,
    log_path: Path,
) -> dict[str, Any]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    missing = [r for r in rows if not r.get("recent")]
    total = len(rows)
    before = total - len(missing)

    if not missing:
        log(f"complete: all {total} accounts already have recent data", log_path)
        return {"enriched": 0, "before": before, "after": before, "total": total, "stopped": "complete"}

    log(f"start: audit={path.name} enriched={before}/{total} batch={batch_size}", log_path)
    enriched = 0
    stopped = "batch_done"

    for row in missing[:batch_size]:
        username = row["user"]["username"]
        tweets, fetch_error = fra.fetch_recent(username, tweet_count, False, timeout_s)
        recent = fra.score_recent(tweets, fetch_error)
        row["recent"] = recent
        row["final_bucket"] = fra.final_bucket(
            row["bucket"],
            int(row.get("score") or 0),
            int(recent["recent_score"]),
            str(recent.get("fetch_status") or ""),
        )
        enriched += 1
        days = recent.get("last_tweet_days")
        inactive = f" inactive={days}d" if days is not None else ""
        log(f"  [{enriched}/{batch_size}] @{username}{inactive} final={row['final_bucket']}", log_path)

        for r in rows:
            if "final_bucket" not in r:
                r["final_bucket"] = r["bucket"]
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if fetch_error and "rate limit" in fetch_error.lower():
            log("rate limit detected — stopping early", log_path)
            stopped = "rate_limit"
            break
        time.sleep(sleep_s)

    after = before + enriched
    if enriched:
        render = ROOT / "scripts" / "render_following_audit_html.py"
        subprocess.run([sys.executable, str(render), str(path)], check=False, cwd=ROOT)
        log(f"html refreshed: {path.with_suffix('.html').name}", log_path)

    log(f"done: enriched={after}/{total} (+{enriched}) stopped={stopped}", log_path)
    return {"enriched": enriched, "before": before, "after": after, "total": total, "stopped": stopped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily safe batch recent enrichment")
    parser.add_argument("--audit", type=Path, help="Path to *_recent.json (default: latest)")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--daily-cap", type=int, default=50, help="Max accounts enriched per calendar day")
    parser.add_argument("--sleep-s", type=float, default=3.0)
    parser.add_argument("--tweet-count", type=int, default=1)
    parser.add_argument("--timeout-s", type=int, default=25)
    parser.add_argument("--force", action="store_true", help="Ignore daily cap")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"daily_enrich_{today}.log"
    state = load_state()

    enriched_today = daily_enriched_today(state)
    if should_skip(state, args.daily_cap, args.force):
        log(
            f"skip: daily cap reached ({enriched_today}/{args.daily_cap}) — use --force to override",
            log_path,
        )
        return

    remaining_today = args.daily_cap - enriched_today
    batch_size = min(args.batch_size, remaining_today)
    if batch_size <= 0:
        log("skip: no quota left today", log_path)
        return

    audit_path = resolve_audit_path(args.audit)
    result = enrich_batch(
        audit_path,
        batch_size=batch_size,
        sleep_s=args.sleep_s,
        tweet_count=args.tweet_count,
        timeout_s=args.timeout_s,
        log_path=log_path,
    )

    new_enriched_today = enriched_today + result["enriched"]
    save_state(
        {
            "audit_path": str(audit_path),
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_run_date": today,
            "last_run_status": "ok" if result["stopped"] != "rate_limit" else "rate_limit",
            "last_batch_enriched": result["enriched"],
            "enriched_today": new_enriched_today,
            "daily_cap": args.daily_cap,
            "total_enriched": result["after"],
            "total_accounts": result["total"],
        }
    )

    if result["stopped"] == "rate_limit":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
