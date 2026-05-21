const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const COOKIES_PATH = path.join(PROJECT_ROOT, 'data', 'x_cookies.json');
const DEFAULT_INPUT = path.join(PROJECT_ROOT, 'data', 'following_audit', 'approved_unfollow.txt');
const KEEP_OVERRIDES = path.join(PROJECT_ROOT, 'data', 'following_audit', 'keep_overrides.txt');

function parseArgs(argv) {
  const args = {
    input: DEFAULT_INPUT,
    execute: false,
    max: 5,
    minDelayMs: 6000,
    maxDelayMs: 12000,
    headless: true,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--execute') args.execute = true;
    else if (token === '--show-browser') args.headless = false;
    else if (token === '--input' && argv[i + 1]) args.input = argv[++i];
    else if (token === '--max' && argv[i + 1]) args.max = Number(argv[++i]);
    else if (token === '--min-delay-ms' && argv[i + 1]) args.minDelayMs = Number(argv[++i]);
    else if (token === '--max-delay-ms' && argv[i + 1]) args.maxDelayMs = Number(argv[++i]);
  }
  if (!Number.isFinite(args.max) || args.max <= 0) throw new Error('Invalid --max');
  if (!Number.isFinite(args.minDelayMs) || !Number.isFinite(args.maxDelayMs) || args.minDelayMs < 0 || args.maxDelayMs < args.minDelayMs) {
    throw new Error('Invalid delay range');
  }
  if (args.execute) {
    if (args.max > 20) throw new Error('For safety, --execute only allows --max <= 20');
    if (args.minDelayMs < 6000) throw new Error('For safety, --execute requires --min-delay-ms >= 6000');
  }
  return args;
}

function normalizeHandle(raw) {
  return raw.trim().replace(/^@/, '').toLowerCase();
}

function readHandleFile(filePath) {
  if (!fs.existsSync(filePath)) return [];
  return fs
    .readFileSync(filePath, 'utf8')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
    .map(normalizeHandle);
}

function randomDelayMs(min, max) {
  if (max <= min) return min;
  return Math.floor(min + Math.random() * (max - min + 1));
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
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

async function run() {
  const args = parseArgs(process.argv);
  if (!fs.existsSync(COOKIES_PATH)) throw new Error(`Cookie file missing: ${COOKIES_PATH}`);

  const inputHandles = readHandleFile(args.input);
  const keepSet = new Set(readHandleFile(KEEP_OVERRIDES));
  const uniqueHandles = [...new Set(inputHandles)].filter((h) => !keepSet.has(h));
  const queue = uniqueHandles.slice(0, args.max);

  console.log(`mode=${args.execute ? 'execute' : 'dry-run'} input=${args.input}`);
  console.log(`loaded=${inputHandles.length} unique=${uniqueHandles.length} queue=${queue.length} keep_overrides=${keepSet.size}`);
  if (!queue.length) {
    console.log('No handles to process.');
    return;
  }

  const cookieData = JSON.parse(fs.readFileSync(COOKIES_PATH, 'utf8'));
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
        results.push({ handle, status: res.ok ? 'unfollowed' : `failed_${res.reason}` });
      }
    } catch (err) {
      results.push({ handle, status: `error_${String(err.message || err).slice(0, 120)}` });
    }

    if (i < queue.length - 1) {
      const waitMs = randomDelayMs(args.minDelayMs, args.maxDelayMs);
      console.log(`wait=${waitMs}ms next=${queue[i + 1]}`);
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
        queue,
        results,
      },
      null,
      2
    )
  );

  console.log(`result_file=${outPath}`);
  for (const item of results) console.log(`- @${item.handle}: ${item.status}`);
}

run().catch((err) => {
  console.error(`fatal=${String(err.message || err)}`);
  process.exit(1);
});
