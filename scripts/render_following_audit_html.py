#!/usr/bin/env python3
"""
Render a following_audit JSON file into a self-contained local HTML review page.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data" / "following_audit"


def default_input() -> Path:
    candidates = sorted(AUDIT_DIR.glob("following_audit_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit("No following_audit_*.json file found under data/following_audit")
    return candidates[0]


def inactive_label(last_days: int | None, fetch_status: str) -> str:
    if last_days is None:
        if fetch_status in ("failed", "empty", "not_checked", ""):
            return "—"
        return "?"
    if last_days == 0:
        return "今天"
    return f"{last_days}d"


def inactive_sort_key(last_days: int | None) -> int:
    if last_days is None:
        return -1
    return last_days


def render_row(row: dict) -> str:
    user = row["user"]
    username = html.escape(str(user.get("username") or ""))
    name = html.escape(str(user.get("name") or ""))
    bio_raw = str(user.get("description") or "")
    bio = html.escape(bio_raw).replace("\n", "<br>")
    reasons = html.escape("; ".join(row.get("reasons") or []))
    recent = row.get("recent") or {}
    recent_score = recent.get("recent_score", "")
    recent_status = html.escape(str(recent.get("fetch_status") or "not_checked"))
    recent_reasons = html.escape("; ".join(recent.get("reasons") or []))
    last_days_raw = recent.get("last_tweet_days")
    last_days: int | None
    if last_days_raw is None or last_days_raw == "":
        last_days = None
    else:
        last_days = int(last_days_raw)
    inactive_text = html.escape(inactive_label(last_days, str(recent.get("fetch_status") or "")))
    last_days_attr = "" if last_days is None else str(last_days)
    inactive_class = "inactive-unknown"
    if last_days is not None:
        if last_days <= 30:
            inactive_class = "inactive-fresh"
        elif last_days <= 90:
            inactive_class = "inactive-warn"
        elif last_days <= 180:
            inactive_class = "inactive-stale"
        else:
            inactive_class = "inactive-dead"
    final_bucket_raw = str(row.get("final_bucket") or row.get("bucket") or "")
    final_bucket = html.escape(final_bucket_raw)
    bucket = html.escape(str(row.get("bucket") or ""))
    score = int(row.get("score") or 0)
    followers = int(user.get("followers") or 0)
    following = int(user.get("following") or 0)
    tweets = int(user.get("tweets") or 0)
    verified = "✓" if user.get("verified") else ""
    search_text = html.escape(f"{username} {name} {bio_raw}".lower(), quote=True)
    url = f"https://x.com/{username}"
    return f"""
    <tr data-bucket="{final_bucket}" data-static-bucket="{bucket}" data-score="{score}" data-handle="{username.lower()}" data-text="{search_text}" data-last-days="{last_days_attr}" data-inactive-sort="{inactive_sort_key(last_days)}">
      <td><input type="checkbox" class="pick" value="{username}"></td>
      <td><span class="badge {final_bucket}">{final_bucket}</span></td>
      <td class="score">{score}</td>
      <td><a href="{url}" target="_blank">@{username}</a><div class="name">{name} {verified}</div></td>
      <td class="num">{followers:,}</td>
      <td class="num">{following:,}</td>
      <td class="num">{tweets:,}</td>
      <td class="inactive {inactive_class}">{inactive_text}</td>
      <td><span class="badge {final_bucket}">{final_bucket}</span></td>
      <td class="score">{recent_score}</td>
      <td>{recent_status}<br><span class="name">{recent_reasons}</span></td>
      <td>{reasons}</td>
      <td class="bio">{bio}</td>
    </tr>
    """


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, help="audit JSON file; default uses latest")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    input_path = args.input or default_input()
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    out = args.out or input_path.with_suffix(".html")

    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("final_bucket") or row.get("bucket") or "unknown")
        counts[key] = counts.get(key, 0) + 1

    body_rows = "\n".join(render_row(row) for row in rows)
    cards = "\n".join(
        f'<div class="card"><b>{count}</b>{html.escape(bucket)}</div>'
        for bucket, count in sorted(counts.items())
    )
    source = html.escape(input_path.name)

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X Following Audit</title>
  <style>
    :root {{ color-scheme: dark; --bg:#09090b; --panel:#111827; --muted:#9ca3af; --line:#27272a; --text:#e5e7eb; --green:#22c55e; --yellow:#eab308; --red:#ef4444; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    header {{ position:sticky; top:0; z-index:2; background:rgba(9,9,11,.95); border-bottom:1px solid var(--line); padding:18px 22px; }}
    h1 {{ margin:0 0 10px; font-size:22px; }}
    .meta {{ color:var(--muted); font-size:13px; margin-bottom:12px; }}
    .controls {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    input[type="search"], select {{ background:#18181b; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:9px 10px; }}
    button {{ background:#2563eb; color:white; border:0; border-radius:8px; padding:9px 12px; cursor:pointer; }}
    button.secondary {{ background:#374151; }}
    main {{ padding:18px 22px; }}
    .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 14px; min-width:140px; }}
    .card b {{ display:block; font-size:22px; margin-bottom:4px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px 8px; vertical-align:top; }}
    th {{ position:sticky; top:94px; background:#0f172a; z-index:1; text-align:left; color:#cbd5e1; }}
    tr:hover {{ background:#111827; }}
    .badge {{ display:inline-block; padding:3px 7px; border-radius:999px; font-size:12px; color:#111827; }}
    .keep {{ background:var(--green); }}
    .maybe {{ background:var(--yellow); }}
    .unfollow_candidate {{ background:var(--red); color:white; }}
    .manual_review {{ background:#f97316; color:white; }}
    .score {{ font-weight:700; }}
    .name, .bio {{ color:var(--muted); }}
    .num {{ text-align:right; white-space:nowrap; }}
    .inactive {{ font-weight:700; white-space:nowrap; }}
    .inactive-fresh {{ color:var(--green); }}
    .inactive-warn {{ color:var(--yellow); }}
    .inactive-stale {{ color:#fb923c; }}
    .inactive-dead {{ color:var(--red); }}
    .inactive-unknown {{ color:var(--muted); }}
    textarea {{ width:100%; min-height:120px; margin-top:12px; background:#18181b; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:10px; }}
    a {{ color:#93c5fd; }}
  </style>
</head>
<body>
  <header>
    <h1>X Following Audit</h1>
    <div class="meta">{len(rows)} accounts · source: {source}</div>
    <div class="controls">
      <input id="q" type="search" placeholder="Search handle / name / bio" size="32">
      <select id="bucket">
        <option value="all">All buckets</option>
        <option value="unfollow_candidate">Unfollow candidate</option>
        <option value="manual_review">Manual review</option>
        <option value="maybe">Maybe</option>
        <option value="keep">Keep</option>
      </select>
      <select id="score">
        <option value="all">All scores</option>
        <option value="lt0">score &lt; 0</option>
        <option value="lt2">score &lt; 2</option>
        <option value="lt4">score &lt; 4</option>
      </select>
      <select id="inactive">
        <option value="all">All activity</option>
        <option value="gt30">未活跃 &gt; 30 天</option>
        <option value="gt90">未活跃 &gt; 90 天</option>
        <option value="gt180">未活跃 &gt; 180 天</option>
        <option value="unknown">未活跃未知</option>
      </select>
      <select id="sort">
        <option value="default">Default order</option>
        <option value="inactive_desc">未活跃天数 ↓</option>
        <option value="inactive_asc">未活跃天数 ↑</option>
      </select>
      <button onclick="exportSelected()">Export selected handles</button>
      <button class="secondary" onclick="selectVisible()">Select visible</button>
      <button class="secondary" onclick="clearChecks()">Clear</button>
    </div>
  </header>
  <main>
    <section class="cards">{cards}</section>
    <table>
      <thead>
        <tr>
          <th></th><th>Bucket (final)</th><th>Score</th><th>Account</th><th>Followers</th><th>Following</th><th>Tweets</th><th>未活跃</th><th>Final</th><th>Recent</th><th>Recent Notes</th><th>Reasons</th><th>Bio</th>
        </tr>
      </thead>
      <tbody>{body_rows}</tbody>
    </table>
    <textarea id="out" placeholder="Exported handles"></textarea>
  </main>
  <script>
    const q = document.getElementById('q');
    const bucket = document.getElementById('bucket');
    const score = document.getElementById('score');
    const inactive = document.getElementById('inactive');
    const sort = document.getElementById('sort');
    const tbody = document.querySelector('tbody');
    const defaultOrder = [...tbody.querySelectorAll('tr')];

    function lastDays(tr) {{
      const raw = tr.dataset.lastDays;
      if (raw === '') return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }}

    function matchesInactive(tr) {{
      const days = lastDays(tr);
      if (inactive.value === 'all') return true;
      if (inactive.value === 'unknown') return days === null;
      if (inactive.value === 'gt30') return days !== null && days > 30;
      if (inactive.value === 'gt90') return days !== null && days > 90;
      if (inactive.value === 'gt180') return days !== null && days > 180;
      return true;
    }}

    function applySort() {{
      const rows = [...tbody.querySelectorAll('tr')];
      if (sort.value === 'default') {{
        defaultOrder.forEach(tr => tbody.appendChild(tr));
        return;
      }}
      rows.sort((a, b) => {{
        const da = Number(a.dataset.inactiveSort);
        const db = Number(b.dataset.inactiveSort);
        if (sort.value === 'inactive_desc') return db - da;
        return da - db;
      }});
      rows.forEach(tr => tbody.appendChild(tr));
    }}

    function applyFilter() {{
      const query = q.value.trim().toLowerCase();
      for (const tr of tbody.querySelectorAll('tr')) {{
        const b = tr.dataset.bucket;
        const s = Number(tr.dataset.score);
        let ok = true;
        if (bucket.value !== 'all' && b !== bucket.value) ok = false;
        if (score.value === 'lt0' && !(s < 0)) ok = false;
        if (score.value === 'lt2' && !(s < 2)) ok = false;
        if (score.value === 'lt4' && !(s < 4)) ok = false;
        if (!matchesInactive(tr)) ok = false;
        if (query && !tr.dataset.text.includes(query)) ok = false;
        tr.style.display = ok ? '' : 'none';
      }}
    }}

    function refresh() {{
      applySort();
      applyFilter();
    }}

    q.addEventListener('input', applyFilter);
    bucket.addEventListener('change', applyFilter);
    score.addEventListener('change', applyFilter);
    inactive.addEventListener('change', applyFilter);
    sort.addEventListener('change', refresh);

    function visibleRows() {{ return [...tbody.querySelectorAll('tr')].filter(tr => tr.style.display !== 'none'); }}
    function selectVisible() {{ visibleRows().forEach(tr => tr.querySelector('.pick').checked = true); }}
    function clearChecks() {{ document.querySelectorAll('.pick').forEach(cb => cb.checked = false); }}
    function exportSelected() {{
      const handles = [...document.querySelectorAll('.pick:checked')].map(cb => '@' + cb.value);
      document.getElementById('out').value = handles.join('\\n');
    }}
  </script>
</body>
</html>
"""
    out.write_text(doc, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
