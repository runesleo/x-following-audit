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

## 1) Static audit

```bash
python3 scripts/following_audit.py --handle your_handle
```

Outputs:
- `data/following_audit/following_raw_<timestamp>.json`
- `data/following_audit/following_audit_<timestamp>.json`

## 2) Recent enrichment

```bash
python3 scripts/following_recent_audit.py
```

Output:
- `data/following_audit/following_audit_<timestamp>_recent.json`

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

## 5) Dry-run first

```bash
node scripts/batch_unfollow_safe.js --input data/following_audit/approved_unfollow.txt --max 5
```

## 6) Execute in small batches

```bash
node scripts/batch_unfollow_safe.js --input data/following_audit/approved_unfollow.txt --max 5 --execute
```

## 7) Keep list

Put protected handles in:
- `data/following_audit/keep_overrides.txt`

These handles are skipped during execution.
