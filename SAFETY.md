# SAFETY

This project is designed for low-risk, human-reviewed account hygiene.

## Authentication and API boundary

- Uses logged-in cookie auth (`auth_token`, `ct0`).
- This is not an official stable X API integration pattern.
- Behavior may break when X UI/API internals change.

## Default safety policy

- Always run `dry-run` before `--execute`.
- Human review is required before execution.
- Recommended batch size: 3-5 handles.
- Recommended interval: random 6-12 seconds.
- Recommended daily cap: <= 20 actions.

## Controls

- Keep list (`keep_overrides.txt`) to prevent accidental unfollow.
- Per-run JSON logs for auditability.
- Stop the batch immediately if login/rate-limit/challenge appears.

## Sharing guidance

- Position as "following audit workflow", not "mass unfollow tool".
- Do not promise growth outcomes.
