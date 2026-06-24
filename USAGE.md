# USAGE

## 0) Cookie auth file

Create:
- `data/x_cookies.json`

Format:

```json
{
  "auth_token": "YOUR_AUTH_TOKEN",
  "ct0": "YOUR_CT0"
}
```

Security notes:
- Treat this file as a live account credential.
- Never commit or share it.
- Recommended: `chmod 600 data/x_cookies.json`.
- The executor enforces strict permission check and will refuse to run if this file is world/group-readable.

## 1) Static audit

```bash
python3 scripts/following_audit.py --handle your_handle
```

One-shot static + recent + HTML:

```bash
python3 scripts/following_audit.py --handle your_handle --with-recent --render-html
```

`--with-recent` enriches `maybe` + `unfollow_candidate` rows with last-active days via `xreach` (no cap by default). Useful flags:

- `--recent-scope maybe_and_candidates|low_confidence|all`
- `--recent-limit 0` — `0` means no cap
- `--recent-sleep-ms 3000`

Outputs:
- `data/following_audit/following_raw_<timestamp>.json`
- `data/following_audit/following_audit_<timestamp>.json`

> If you don't use `xreach`, skip this step and place an existing audit JSON under `data/following_audit/`.

## 2) Recent enrichment

```bash
python3 scripts/following_recent_audit.py
```

By default this enriches all `maybe` + `unfollow_candidate` accounts (no `--limit` cap). Each row gets:

- `recent.last_tweet_days` — days since last tweet
- `recent.last_active_at` — ISO timestamp of latest tweet
- `final_bucket` — static + recent combined verdict

Useful flags:

- `--scope maybe_and_candidates|low_confidence|all`
- `--limit 0` — cap enriched accounts; `0` = no cap
- `--sleep-ms 3000`

Output:
- `data/following_audit/following_audit_<timestamp>_recent.json`

> If you don't use `xreach`, you can skip this step and render HTML from your existing audit JSON directly.

## 3) HTML review page

```bash
python3 scripts/render_following_audit_html.py
```

Offline preview with sample data:

```bash
python3 scripts/render_following_audit_html.py samples/following_audit.sample.json
```

The HTML page includes:

- **未活跃** column (`last_tweet_days`, color-coded)
- Filters: 未活跃 > 30 / > 90 / > 180 天, 未活跃未知
- Sort: 未活跃天数 ↑ / ↓

Output:
- `data/following_audit/following_audit_<timestamp>_recent.html`

## 4) Prepare approved list

Create:
- `data/following_audit/approved_unfollow.txt`

One handle per line:

```txt
@handle_a
@handle_b
```

You can bootstrap from samples:

```bash
cp samples/approved_unfollow.sample.txt data/following_audit/approved_unfollow.txt
cp samples/keep_overrides.sample.txt data/following_audit/keep_overrides.txt
```

## 5) Dry-run first

```bash
node scripts/batch_unfollow_safe.js --input data/following_audit/approved_unfollow.txt --max 5
```

## 6) Execute in small batches

```bash
node scripts/batch_unfollow_safe.js \
  --input data/following_audit/approved_unfollow.txt \
  --max 5 \
  --daily-cap 20 \
  --execute \
  --confirm-execute UNFOLLOW
```

Safety guards in execute mode:
- `--confirm-execute UNFOLLOW` is mandatory.
- Daily quota is enforced via `--daily-cap` (default 20/day, persisted in `data/following_audit/unfollow_quota_state.json`).
- Invalid handles are rejected (`^[A-Za-z0-9_]{1,15}$`).
- Post-click verification checks follow state before counting a successful action.

## 7) Keep list

Put protected handles in:
- `data/following_audit/keep_overrides.txt`

These handles are skipped during execution.
