#!/usr/bin/env python3
"""Continuous following loop planner (read-only, standard library only).

Turns signals you already have into today's follow / unfollow plan. It never touches an account:
review the plan, then act with `batch_unfollow_safe.js` (or by hand) in small batches.

Inputs (JSON, see samples/loop/):
  --config     principles: source priority, caps, thresholds, probation window
  --following  accounts you follow now: [{"handle", "last_post_days", "verdict", "confidence",
               "prev_verdict", "contribution", "noise_days", "protected"}]
               verdict/confidence come from your own judge (rules, a model, or you):
               keep | offtopic | spam | relay
  --candidates accounts you might follow: [{"handle", "source", "why"}]
  --actions    your action log, one JSON per line: {"at", "handle", "action": follow|unfollow, "ok", "source"}

Output: plan JSON on stdout (or Markdown with --format md). Principles: docs/follow-principles.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
DEFAULTS = {
    "source_priority": ["project", "official", "proven", "interaction", "quoted"],
    "probation_sources": ["proven", "interaction"],
    "probation_days": [30, 45],
    "inactive_days": 60,
    "noise_days": 3,
    "follow_daily": 5,
    "unfollow_daily": 10,
    "following_cap": 800,
}
LABEL = {"inactive": "no post for {n}+ days", "offtopic": "recent posts are off your topics",
         "spam": "mostly ads / shilling / engagement bait", "relay": "mostly reposts others, never useful to you",
         "noise": "judged noise in your timeline on {n}+ days, never useful", "probation": "followed {n} days ago, contributed nothing since"}


def unfollow_plan(following: list[dict], actions: list[dict], cfg: dict, today: dt.date) -> list[dict]:
    """Unfollow candidates with a reason, strongest evidence first. Protected accounts never appear."""
    last: dict[str, dict] = {}
    for a in actions:
        if a.get("action") in ("follow", "unfollow") and a.get("handle"):
            last[a["handle"].lower()] = a
    out = []
    for acc in following:
        h = acc.get("handle", "")
        if acc.get("protected") or not HANDLE.fullmatch(h):
            continue
        v, conf, contrib = acc.get("verdict"), acc.get("confidence"), int(acc.get("contribution") or 0)
        days = acc.get("last_post_days")
        reason = ""
        if days is not None and days > cfg["inactive_days"]:
            reason = LABEL["inactive"].format(n=cfg["inactive_days"])
        elif v in ("offtopic", "spam") and (conf == "high" or (conf == "medium" and acc.get("prev_verdict") == v)):
            reason = LABEL[v]
        elif v == "relay" and conf == "high" and contrib == 0:
            reason = LABEL["relay"]
        elif int(acc.get("noise_days") or 0) >= cfg["noise_days"] and contrib == 0:
            reason = LABEL["noise"].format(n=cfg["noise_days"])
        else:
            r = last.get(h.lower())
            if r and r.get("action") == "follow" and r.get("ok") and r.get("source") in cfg["probation_sources"] and contrib == 0:
                try:
                    age = (today - dt.date.fromisoformat(str(r.get("at", ""))[:10])).days
                except ValueError:
                    age = -1
                lo, hi = cfg["probation_days"]
                if lo <= age <= hi:
                    reason = LABEL["probation"].format(n=age)
        if reason:
            out.append({"handle": h, "reason": reason})
    return out[: cfg["unfollow_daily"]]


def follow_plan(following: list[dict], candidates: list[dict], cfg: dict, unfollows: int, used_today: int) -> list[dict]:
    """Candidates by source priority, deduplicated, within the daily cap and the total following cap."""
    have = {a.get("handle", "").lower() for a in following}
    rank = {s: i for i, s in enumerate(cfg["source_priority"])}
    seen, ordered = set(), []
    for c in sorted(candidates, key=lambda c: rank.get(c.get("source"), len(rank))):
        h = c.get("handle", "").lstrip("@")
        if c.get("source") not in rank or not HANDLE.fullmatch(h) or h.lower() in have or h.lower() in seen:
            continue
        seen.add(h.lower())
        ordered.append({"handle": h, "source": c["source"], "why": c.get("why", "")})
    room = min(cfg["follow_daily"] - used_today, cfg["following_cap"] - (len(following) - unfollows))
    return ordered[: max(0, room)]


def build(cfg: dict, following: list[dict], candidates: list[dict], actions: list[dict], today: dt.date) -> dict:
    cfg = {**DEFAULTS, **cfg}
    used = sum(1 for a in actions if a.get("action") == "follow" and a.get("ok") and str(a.get("at", ""))[:10] == today.isoformat())
    drop = unfollow_plan(following, actions, cfg, today)
    add = follow_plan(following, candidates, cfg, len(drop), used)
    return {"date": today.isoformat(), "following": len(following), "following_cap": cfg["following_cap"],
            "unfollow": drop, "follow": add, "note": "plan only: review it, then act in small batches"}


def to_md(plan: dict) -> str:
    lines = [f"# Following loop plan {plan['date']}", "",
             f"Following {plan['following']} (cap {plan['following_cap']}). Plan only, nothing was clicked.", "",
             f"## Unfollow ({len(plan['unfollow'])})", ""]
    lines += [f"- @{x['handle']}: {x['reason']}" for x in plan["unfollow"]] or ["- (none)"]
    lines += ["", f"## Follow ({len(plan['follow'])})", ""]
    lines += [f"- @{x['handle']} [{x['source']}] {x['why']}".rstrip() for x in plan["follow"]] or ["- (none)"]
    lines += ["", "---", "x-following-audit by [@runes_leo](https://x.com/runes_leo). Useful? A star or a follow is welcome, never required."]
    return "\n".join(lines) + "\n"


def read_json(path: str | None, default):
    if not path:
        return default
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan today's follow / unfollow actions from your own signals (read-only).")
    ap.add_argument("--config")
    ap.add_argument("--following", required=True)
    ap.add_argument("--candidates")
    ap.add_argument("--actions")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    plan = build(read_json(args.config, {}), read_json(args.following, []), read_json(args.candidates, []),
                 read_jsonl(args.actions), today)
    sys.stdout.write(to_md(plan) if args.format == "md" else json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
