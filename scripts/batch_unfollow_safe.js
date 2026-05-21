const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const COOKIES_PATH = path.join(PROJECT_ROOT, 'data', 'x_cookies.json');
const DEFAULT_INPUT = path.join(PROJECT_ROOT, 'data', 'following_audit', 'approved_unfollow.txt');
const KEEP_OVERRIDES = path.join(PROJECT_ROOT, 'data', 'following_audit', 'keep_overrides.txt');
const DEFAULT_QUOTA_STATE = path.join(PROJECT_ROOT, 'data', 'following_audit', 'unfollow_quota_state.json');
const HANDLE_RE = /^[a-z0-9_]{1,15}$/;

function parseArgs(argv) {
  const args = {
    input: DEFAULT_INPUT,
    execute: false,
    confirmExecute: '',
    max: 5,
    minDelayMs: 6000,
    maxDelayMs: 12000,
    dailyCap: 20,
    stateFile: DEFAULT_QUOTA_STATE,
    headless: true,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--execute') args.execute = true;
    else if (token === '--confirm-execute' && argv[i + 1]) args.confirmExecute = String(argv[++i]);
    else if (token === '--show-browser') args.headless = false;
    else if (token === '--input' && argv[i + 1]) args.input = argv[++i];
    else if (token === '--max' && argv[i + 1]) args.max = Number(argv[++i]);
    else if (token === '--min-delay-ms' && argv[i + 1]) args.minDelayMs = Number(argv[++i]);
    else if (token === '--max-delay-ms' && argv[i + 1]) args.maxDelayMs = Number(argv[++i]);
    else if (token === '--daily-cap' && argv[i + 1]) args.dailyCap = Number(argv[++i]);
    else if (token === '--state-file' && argv[i + 1]) args.stateFile = argv[++i];
  }
  if (!Number.isFinite(args.max) || args.max <= 0) throw new Error('Invalid --max');
  if (!Number.isFinite(args.dailyCap) || args.dailyCap <= 0) throw new Error('Invalid --daily-cap');
  if (!Number.isFinite(args.minDelayMs) || !Number.isFinite(args.maxDelayMs) || args.minDelayMs < 0 || args.maxDelayMs < args.minDelayMs) {
    throw new Error('Invalid delay range');
  }
  if (args.execute) {
    if (args.confirmExecute !== 'UNFOLLOW') {
      throw new Error('For safety, --execute requires --confirm-execute UNFOLLOW');
    }
    if (args.max > 20) throw new Error('For safety, --execute only allows --max <= 20');
    if (args.minDelayMs < 6000) throw new Error('For safety, --execute requires --min-delay-ms >= 6000');
  }
  return args;
}

function normalizeHandle(raw) {
  return raw.trim().replace(/^@/, '').toLowerCase();
}

function isValidHandle(handle) {
  return HANDLE_RE.test(handle);
}

function readHandleFile(filePath, { strict }) {
  if (!fs.existsSync(filePath)) {
    if (strict) throw new Error(`Handle file missing: ${filePath}`);
    return [];
  }
  const handles = [];
  const invalid = [];
  const lines = fs.readFileSync(filePath, 'utf8').split('\n');
  for (let idx = 0; idx < lines.length; idx += 1) {
    const line = lines[idx].trim();
    if (!line || line.startsWith('#')) continue;
    const handle = normalizeHandle(line);
    if (!isValidHandle(handle)) {
      invalid.push({ line: idx + 1, value: line });
      continue;
    }
    handles.push(handle);
  }
  if (strict && invalid.length) {
    const sample = invalid.slice(0, 8).map((item) => `line ${item.line}: ${item.value}`).join(' | ');
    throw new Error(`Invalid handles in ${filePath}: ${sample}`);
  }
  if (!strict && invalid.length) {
    console.warn(`warning=ignored_invalid_handles file=${filePath} count=${invalid.length}`);
  }
  return handles;
}

function randomDelayMs(min, max) {
  if (max <= min) return min;
  return Math.floor(min + Math.random() * (max - min + 1));
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function shanghaiDayKey() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());
}

function loadQuotaState(statePath) {
  if (!fs.existsSync(statePath)) return { day: shanghaiDayKey(), executed: 0 };
  try {
    const payload = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    return {
      day: String(payload.day || shanghaiDayKey()),
      executed: Number.isFinite(payload.executed) ? payload.executed : 0,
    };
  } catch (err) {
    return { day: shanghaiDayKey(), executed: 0 };
  }
}

function saveQuotaState(statePath, state) {
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2));
}

function ensureCookieFileSafe(cookiePath) {
  if (!fs.existsSync(cookiePath)) {
    throw new Error(`Cookie file missing: ${cookiePath}`);
  }
  const stat = fs.statSync(cookiePath);
  if ((stat.mode & 0o077) !== 0) {
    throw new Error(`Cookie file permissions too open: ${cookiePath}. Run: chmod 600 ${cookiePath}`);
  }
}

async function gotoProfile(page, handle) {
  await page.goto(`https://x.com/${handle}`, { waitUntil: 'networkidle2', timeout: 60000 });
  await sleep(1500);
}

async function detectUnfollowState(page) {
  return page.evaluate(() => {
    const result = { hasFollowingBtn: false, hasFollowBtn: false };
    const buttons = Array.from(document.querySelectorAll('button'));
    for (const btn of buttons) {
      const txt = (btn.textContent || '').trim().toLowerCase();
      if (txt.includes('following') || txt.includes('已关注') || txt.includes('正在关注')) result.hasFollowingBtn = true;
      if (txt === 'follow' || txt === '关注') result.hasFollowBtn = true;
    }
    return result;
  });
}

async function clickUnfollow(page) {
  const clickedFollowing = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    for (const btn of buttons) {
      const txt = (btn.textContent || '').trim().toLowerCase();
      if (txt.includes('following') || txt.includes('已关注') || txt.includes('正在关注')) {
        btn.click();
        return true;
      }
    }
    return false;
  });
  if (!clickedFollowing) return { ok: false, reason: 'following_button_not_found' };

  await sleep(1200);
  const clickedConfirm = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    for (const btn of buttons) {
      const txt = (btn.textContent || '').trim().toLowerCase();
      if (txt === 'unfollow' || txt === '取消关注') {
        btn.click();
        return true;
      }
    }
    return false;
  });
  if (!clickedConfirm) return { ok: false, reason: 'confirm_button_not_found' };

  await sleep(2200);
  return { ok: true };
}

function isFailureStatus(status) {
  return status.startsWith('failed_') || status.startsWith('error_') || status === 'state_unknown';
}

async function run() {
  const args = parseArgs(process.argv);
  ensureCookieFileSafe(COOKIES_PATH);

  const inputHandles = readHandleFile(args.input, { strict: true });
  const keepSet = new Set(readHandleFile(KEEP_OVERRIDES, { strict: false }));
  const uniqueHandles = [...new Set(inputHandles)].filter((h) => !keepSet.has(h));
  const quotaState = loadQuotaState(args.stateFile);
  const dayKey = shanghaiDayKey();
  const alreadyExecuted = quotaState.day === dayKey ? quotaState.executed : 0;
  const remainingQuota = Math.max(0, args.dailyCap - alreadyExecuted);
  const hardLimit = args.execute ? Math.min(args.max, remainingQuota) : args.max;
  const queue = uniqueHandles.slice(0, hardLimit);

  console.log(`mode=${args.execute ? 'execute' : 'dry-run'} input=${args.input}`);
  console.log(
    `loaded=${inputHandles.length} unique=${uniqueHandles.length} queue=${queue.length} keep_overrides=${keepSet.size} daily_cap=${args.dailyCap} already_executed_today=${alreadyExecuted}`
  );
  if (args.execute && remainingQuota <= 0) {
    throw new Error(`Daily cap reached: executed=${alreadyExecuted}, cap=${args.dailyCap}`);
  }
  if (!queue.length) {
    console.log('No handles to process.');
    return;
  }

  const cookieData = JSON.parse(fs.readFileSync(COOKIES_PATH, 'utf8'));
  if (!cookieData.auth_token || !cookieData.ct0) {
    throw new Error(`Cookie file missing required fields auth_token/ct0: ${COOKIES_PATH}`);
  }
  const launchArgs = [];
  if (process.env.PUPPETEER_NO_SANDBOX === '1') {
    launchArgs.push('--no-sandbox', '--disable-setuid-sandbox');
  }
  const browser = await puppeteer.launch({
    headless: args.headless,
    args: launchArgs,
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  await page.setCookie(
    { name: 'auth_token', value: cookieData.auth_token, domain: '.x.com' },
    { name: 'ct0', value: cookieData.ct0, domain: '.x.com' }
  );

  const results = [];
  let consecutiveFailures = 0;
  let executedVerified = 0;
  for (let i = 0; i < queue.length; i += 1) {
    const handle = queue[i];
    try {
      await gotoProfile(page, handle);
      const state = await detectUnfollowState(page);
      if (state.hasFollowBtn && !state.hasFollowingBtn) {
        results.push({ handle, status: 'already_not_following' });
      } else if (!state.hasFollowingBtn) {
        results.push({ handle, status: 'state_unknown' });
      } else if (!args.execute) {
        results.push({ handle, status: 'dry_run_would_unfollow' });
      } else {
        const res = await clickUnfollow(page);
        if (!res.ok) {
          results.push({ handle, status: `failed_${res.reason}` });
        } else {
          const verify = await detectUnfollowState(page);
          if (verify.hasFollowBtn && !verify.hasFollowingBtn) {
            results.push({ handle, status: 'unfollowed_verified' });
            executedVerified += 1;
          } else if (verify.hasFollowingBtn) {
            results.push({ handle, status: 'failed_verify_still_following' });
          } else {
            results.push({ handle, status: 'unfollowed_unverified' });
          }
        }
      }
    } catch (err) {
      results.push({ handle, status: `error_${String(err.message || err).slice(0, 120)}` });
    }

    const current = results[results.length - 1];
    if (args.execute) {
      if (isFailureStatus(current.status)) {
        consecutiveFailures += 1;
      } else {
        consecutiveFailures = 0;
      }
      if (consecutiveFailures >= 3) {
        console.log('abort=too_many_consecutive_failures');
        break;
      }
    }

    if (i < queue.length - 1) {
      const waitMs = randomDelayMs(args.minDelayMs, args.maxDelayMs);
      console.log(`wait=${waitMs}ms`);
      await sleep(waitMs);
    }
  }

  await browser.close();
  const outDir = path.join(PROJECT_ROOT, 'data', 'following_audit');
  fs.mkdirSync(outDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outPath = path.join(outDir, `unfollow_run_${stamp}.json`);
  fs.writeFileSync(
    outPath,
    JSON.stringify(
      {
        timestamp: new Date().toISOString(),
        mode: args.execute ? 'execute' : 'dry-run',
        input: args.input,
        daily_cap: args.dailyCap,
        already_executed_today: alreadyExecuted,
        verified_executed_this_run: executedVerified,
        queue,
        results,
      },
      null,
      2
    )
  );
  fs.chmodSync(outPath, 0o600);

  if (args.execute) {
    const nextState = {
      day: dayKey,
      executed: alreadyExecuted + executedVerified,
      updated_at: new Date().toISOString(),
    };
    saveQuotaState(args.stateFile, nextState);
  }

  console.log(`result_file=${outPath}`);
  for (const item of results) console.log(`- @${item.handle}: ${item.status}`);
}

run().catch((err) => {
  console.error(`fatal=${String(err.message || err)}`);
  process.exit(1);
});
