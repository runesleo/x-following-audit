#!/usr/bin/env python3
"""
Add recent activity/content quality signals to a following audit file.

This is read-only with respect to X. It only fetches recent tweets for selected
low-confidence candidates and writes an enriched JSON file.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data" / "following_audit"

CORE_KEYWORDS = [
    "ai",
    "agent",
    "claude",
    "codex",
    "cursor",
    "openai",
    "anthropic",
    "llm",
    "prediction",
    "polymarket",
    "kalshi",
    "quant",
    "trading",
    "builder",
    "developer",
    "startup",
    "github",
    "crypto",
    "web3",
    "defi",
    "大模型",
    "人工智能",
    "预测市场",
    "量化",
    "交易",
    "开发",
    "独立开发",
    "创业",
]

LOW_QUALITY_TERMS = [
    "airdrop",
    "抽奖",
    "白名单",
    r"follow\s*(back|me|4follow)",
    "转发",
    "giveaway",
    "私信",
    "signal",
    "喊单",
    "暴富",
    "100x",
]


def latest_static_audit_file() -> Path:
    candidates = sorted(
        AUDIT_DIR.glob("following_audit_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.name.endswith("_recent.json"):
            continue
        return path
    raise SystemExit("No following_audit_*.json file found under data/following_audit")


def extract_json(stdout: str) -> dict[str, Any]:
    start = stdout.find('{"items"')
    if start == -1:
        return {"items": []}
    payload, _ = json.JSONDecoder().raw_decode(stdout[start:])
    return payload


def fetch_recent(handle: str, count: int, include_replies: bool, timeout_s: int) -> tuple[list[dict[str, Any]], str | None]:
    cmd = ["xreach", "tweets", handle, "--count", str(count), "--max-pages", "1", "--delay", "300", "--plain"]
    if include_replies:
        cmd.append("--replies")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return [], "timeout"
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip().splitlines()[0:1]
        return [], message[0] if message else "xreach_error"
    return extract_json(result.stdout + result.stderr).get("items", []), None


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def contains_term(text: str, term: str) -> bool:
    if any(ord(ch) > 127 for ch in term):
        return term.lower() in text
    pattern = rf"(?<![a-z0-9_]){term}(?![a-z0-9_])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def matching_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if contains_term(text, term.lower())]


def score_recent(tweets: list[dict[str, Any]], fetch_error: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    score = 0
    reasons: list[str] = []
    if fetch_error:
        return {
            "recent_score": 0,
            "reasons": [f"recent fetch failed: {fetch_error}"],
            "last_tweet_days": None,
            "last_active_at": None,
            "sample": [],
            "fetch_status": "failed",
        }
    if not tweets:
        return {
            "recent_score": -3,
            "reasons": ["no recent tweets returned"],
            "last_tweet_days": None,
            "last_active_at": None,
            "sample": [],
            "fetch_status": "empty",
        }

    dates = [parse_date(t.get("createdAt")) for t in tweets]
    dates = [d for d in dates if d is not None]
    last_days = None
    last_active_at = None
    if dates:
        latest = max(dates)
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        last_days = (now - latest).days
        last_active_at = latest.isoformat()
        if last_days <= 30:
            score += 3
            reasons.append(f"active within {last_days}d")
        elif last_days <= 90:
            score += 1
            reasons.append(f"active within {last_days}d")
        else:
            score -= 4
            reasons.append(f"inactive {last_days}d")

    texts = [str(t.get("text") or "") for t in tweets]
    joined = "\n".join(texts).lower()
    core_hits = matching_terms(joined, CORE_KEYWORDS)
    if core_hits:
        score += min(len(core_hits), 5)
        reasons.append("recent core topics: " + ", ".join(core_hits[:5]))
    else:
        score -= 2
        reasons.append("recent tweets off-core")

    low_hits = matching_terms(joined, LOW_QUALITY_TERMS)
    if low_hits:
        score -= min(len(low_hits) * 2, 6)
        reasons.append("low-quality/marketing terms: " + ", ".join(low_hits[:4]))

    original_like = [t for t in tweets if not t.get("isReply") and not t.get("isRetweet")]
    if len(original_like) >= 3:
        score += 2
        reasons.append(f"{len(original_like)} original-like recent posts")
    elif len(original_like) == 0:
        score -= 2
        reasons.append("no original-like recent posts")

    sample = [text.replace("\n", " ")[:180] for text in texts[:3]]
    return {
        "recent_score": score,
        "reasons": reasons,
        "last_tweet_days": last_days,
        "last_active_at": last_active_at,
        "sample": sample,
        "fetch_status": "ok",
    }


def final_bucket(static_bucket: str, static_score: int, recent_score: int, fetch_status: str | None = None) -> str:
    if fetch_status == "failed" and static_score > -6:
        return "manual_review"
    total = static_score + recent_score
    if static_bucket == "unfollow_candidate" and recent_score < 2:
        return "unfollow_candidate"
    if total <= -4:
        return "unfollow_candidate"
    if total < 5:
        return "manual_review"
    return "keep"


def should_enrich_low_confidence(row: dict[str, Any], max_static_score: int) -> bool:
    return row.get("bucket") == "unfollow_candidate" or int(row.get("score") or 0) <= max_static_score


def select_candidates(rows: list[dict[str, Any]], scope: str, max_static_score: int) -> list[dict[str, Any]]:
    if scope == "all":
        return list(rows)
    if scope == "low_confidence":
        return [row for row in rows if should_enrich_low_confidence(row, max_static_score)]
    if scope == "maybe_and_candidates":
        return [row for row in rows if row.get("bucket") in ("maybe", "unfollow_candidate")]
    raise ValueError(f"unknown scope: {scope}")


def enrich_audit_rows(
    rows: list[dict[str, Any]],
    *,
    scope: str = "maybe_and_candidates",
    max_static_score: int = 0,
    limit: int = 0,
    tweet_count: int = 10,
    include_replies: bool = False,
    sleep_ms: int = 3000,
    timeout_s: int = 15,
) -> dict[str, int]:
    candidates = select_candidates(rows, scope, max_static_score)
    candidates = sorted(candidates, key=lambda row: int(row.get("score") or 0))
    if limit > 0:
        candidates = candidates[:limit]
    selected = {row["user"]["username"] for row in candidates}
    stats = {"selected": len(selected), "enriched": 0, "stopped_early": 0}

    for row in rows:
        username = row["user"]["username"]
        if username not in selected:
            continue
        tweets, fetch_error = fetch_recent(username, tweet_count, include_replies, timeout_s)
        recent = score_recent(tweets, fetch_error)
        row["recent"] = recent
        row["final_bucket"] = final_bucket(
            row["bucket"],
            int(row.get("score") or 0),
            int(recent["recent_score"]),
            str(recent.get("fetch_status") or ""),
        )
        stats["enriched"] += 1
        last_days = recent.get("last_tweet_days")
        inactive = f" inactive={last_days}d" if last_days is not None else ""
        print(
            f"[{stats['enriched']}/{stats['selected']}] @{username}: "
            f"static={row['score']} recent={recent['recent_score']} final={row['final_bucket']}{inactive}"
        )
        if fetch_error and "rate limit" in fetch_error.lower():
            print("rate limit detected; stopping this batch to protect account health")
            stats["stopped_early"] = 1
            break
        time.sleep(sleep_ms / 1000)

    for row in rows:
        if "final_bucket" not in row:
            row["final_bucket"] = row["bucket"]

    return stats


def enrich_audit_file(
    input_path: Path,
    out_path: Path | None = None,
    **kwargs: Any,
) -> Path:
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    stats = enrich_audit_rows(rows, **kwargs)
    out = out_path or input_path.with_name(input_path.stem + "_recent.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"written {out} · selected={stats['selected']} enriched={stats['enriched']}"
        + (" · stopped_early=1" if stats["stopped_early"] else "")
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, help="static audit JSON; default is latest file")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--scope",
        choices=("maybe_and_candidates", "low_confidence", "all"),
        default="maybe_and_candidates",
        help="which accounts to fetch recent tweets for (default: all maybe + unfollow_candidate)",
    )
    parser.add_argument("--max-static-score", type=int, default=0, help="only used with --scope low_confidence")
    parser.add_argument("--limit", type=int, default=0, help="cap enriched accounts; 0 = no cap")
    parser.add_argument("--tweet-count", type=int, default=10)
    parser.add_argument("--include-replies", action="store_true")
    parser.add_argument("--sleep-ms", type=int, default=3000)
    parser.add_argument("--timeout-s", type=int, default=15)
    args = parser.parse_args()

    input_path = args.input or latest_static_audit_file()
    enrich_audit_file(
        input_path,
        args.out,
        scope=args.scope,
        max_static_score=args.max_static_score,
        limit=args.limit,
        tweet_count=args.tweet_count,
        include_replies=args.include_replies,
        sleep_ms=args.sleep_ms,
        timeout_s=args.timeout_s,
    )


if __name__ == "__main__":
    main()
