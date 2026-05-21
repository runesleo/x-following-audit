#!/usr/bin/env python3
"""
Fetch and classify an X following list for manual pruning.

Read-only with respect to X: this script never unfollows accounts.
It fetches following data via xreach and creates a conservative
keep/maybe/unfollow_candidate audit file.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "following_audit"
DEFAULT_KEEP_OVERRIDES = OUT_DIR / "keep_overrides.txt"

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
    "founder",
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

SPAM_PATTERNS = [
    r"18\+|🔞|onlyfans|fansly",
    r"airdrop\s*(hunter|farming)",
    r"follow\s*(back|me|4follow)",
    r"signal\s*(group|channel)",
    r"passive\s*income",
]


def extract_json(stdout: str) -> dict[str, Any]:
    start = stdout.find('{"items"')
    if start == -1:
        raise SystemExit("Could not find JSON payload in xreach output")
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(stdout[start:])
    return payload


def fetch_following(handle: str, max_pages: int, delay_ms: int) -> dict[str, Any]:
    cmd = [
        "xreach",
        "following",
        handle,
        "--count",
        "100",
        "--max-pages",
        str(max_pages),
        "--delay",
        str(delay_ms),
        "--plain",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    return extract_json(result.stdout + result.stderr)


def normalize_user(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("restId") or raw.get("id"),
        "username": raw.get("screenName") or raw.get("username"),
        "name": raw.get("name") or "",
        "description": raw.get("description") or "",
        "followers": raw.get("followersCount") or raw.get("followers") or 0,
        "following": raw.get("followingCount") or raw.get("following") or 0,
        "tweets": raw.get("tweetCount") or raw.get("tweets") or 0,
        "verified": bool(raw.get("isBlueVerified") or raw.get("verified")),
        "protected": bool(raw.get("protected")),
    }


def normalize_handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def load_handle_set(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    handles: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        handles.add(normalize_handle(value))
    return handles


def apply_keep_overrides(rows: list[dict[str, Any]], keep_overrides: set[str]) -> None:
    if not keep_overrides:
        return
    for row in rows:
        username = normalize_handle(str(row.get("user", {}).get("username") or ""))
        if username not in keep_overrides:
            continue
        row["bucket"] = "keep"
        row["final_bucket"] = "keep"
        row["score"] = max(int(row.get("score") or 0), 4)
        reasons = row.setdefault("reasons", [])
        if "manual keep override" not in reasons:
            reasons.append("manual keep override")


def classify(user: dict[str, Any]) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    bio = user["description"].lower()
    followers = int(user["followers"] or 0)
    following = int(user["following"] or 0)
    tweets = int(user["tweets"] or 0)

    matched = [kw for kw in CORE_KEYWORDS if kw.lower() in bio]
    if matched:
        score += min(len(matched) * 2, 8)
        reasons.append("core keywords: " + ", ".join(matched[:4]))
    else:
        score -= 2
        reasons.append("no core keywords")

    if followers >= 50_000:
        score += 5
        reasons.append("large account")
    elif followers >= 5_000:
        score += 2

    if following and followers:
        ratio = followers / following
        if ratio < 0.05:
            score -= 5
            reasons.append(f"very low follower/following ratio {ratio:.2f}")
        elif ratio < 0.2:
            score -= 2
            reasons.append(f"low follower/following ratio {ratio:.2f}")
        elif ratio > 3:
            score += 2

    if tweets == 0:
        score -= 5
        reasons.append("no tweets")
    elif tweets < 20:
        score -= 2
        reasons.append(f"few tweets: {tweets}")
    elif tweets > 500:
        score += 1

    if user["verified"]:
        score += 1

    for pattern in SPAM_PATTERNS:
        if re.search(pattern, bio, re.IGNORECASE):
            score -= 8
            reasons.append("spam/adult/airdrop pattern")
            break

    if user["protected"]:
        score -= 1
        reasons.append("protected")

    if score <= -4:
        bucket = "unfollow_candidate"
    elif score < 4:
        bucket = "maybe"
    else:
        bucket = "keep"
    return bucket, score, reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handle", required=True, help="Target handle, e.g. runes_leo")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--delay-ms", type=int, default=1000)
    parser.add_argument("--from-file", type=Path)
    parser.add_argument("--keep-overrides", type=Path, default=DEFAULT_KEEP_OVERRIDES)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.from_file:
        payload = json.loads(args.from_file.read_text(encoding="utf-8"))
    else:
        payload = fetch_following(args.handle, args.max_pages, args.delay_ms)
        raw_path = OUT_DIR / f"following_raw_{stamp}.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    users = [normalize_user(item) for item in payload.get("items", [])]
    rows = []
    for user in users:
        bucket, score, reasons = classify(user)
        rows.append({"bucket": bucket, "score": score, "reasons": reasons, "user": user})

    keep_overrides = load_handle_set(args.keep_overrides)
    apply_keep_overrides(rows, keep_overrides)

    rows.sort(key=lambda row: (row["bucket"], row["score"]))
    audit_path = OUT_DIR / f"following_audit_{stamp}.json"
    audit_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1

    print(f"fetched={len(users)} complete={payload.get('complete')} pagesLoaded={payload.get('pagesLoaded')}")
    print("counts=" + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"audit={audit_path}")
    print("\nTop unfollow candidates:")
    for row in [r for r in rows if r["bucket"] == "unfollow_candidate"][:30]:
        user = row["user"]
        print(
            f"- @{user['username']} score={row['score']} followers={user['followers']} "
            f"tweets={user['tweets']} :: {'; '.join(row['reasons'][:3])}"
        )


if __name__ == "__main__":
    main()
