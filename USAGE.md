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

Outputs:
- `data/following_audit/following_raw_<timestamp>.json`
- `data/following_audit/following_audit_<timestamp>.json`

> If you don't use `xreach`, skip this step and place an existing audit JSON under `data/following_audit/`.

## 2) Recent enrichment

```bash
python3 scripts/following_recent_audit.py
```

Output:
- `data/following_audit/following_audit_<timestamp>_recent.json`

> If you don't use `xreach`, you can skip this step and render HTML from your existing audit JSON directly.

## 3) HTML review page

```bash
python3 scripts/render_following_audit_html.py
```

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
