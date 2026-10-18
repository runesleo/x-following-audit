# Follow principles

中文: [follow-principles.zh.md](./follow-principles.zh.md)

Your following list does two jobs: it decides what you read every day (and nudges what the timeline recommends), and it tells visitors what circle you belong to. Prune it with rules for both what to drop and what to add, or it only ever shrinks or bloats.

## Add, in this order

1. **Projects you track**: their official accounts. First-hand news lands there first.
2. **Official sources in your field**: the labs, tools and platforms you use.
3. **Proven sources**: accounts whose posts you actually picked, saved or reposted lately.
4. **People you talk to**: real people you replied to.
5. **Authors you quoted.**

Prefer the original source over the account that repeats it.

## Drop

- No post for a long time (default 60 days).
- Recent posts are off your topics (high confidence; medium needs two reviews in a row).
- Mostly ads, shilling, giveaways or follow-for-follow.
- Mostly reposting others, with no first-hand work or judgement, *and* never useful to you.
- Repeatedly judged noise in your timeline and never useful.
- **Probation over, nothing contributed**: accounts added from "proven" or "people you talk to" are re-checked 30–45 days later. Officials and tracked projects have no probation.

## Size

- Set a total cap. At the cap, adding means dropping first, so the list only gets sharper.
- Cap daily follows and unfollows; stop at the first anomaly (login wall, challenge, rate limit).

## Never touch

A keep list you control (`keep_overrides.txt`): partners, friends, accounts you simply like. An undo should always add the account to it.

`scripts/follow_loop_plan.py` applies these rules to your own signals and prints a plan; it never clicks.
