#!/usr/bin/env node
/**
 * Standalone Tesco sign-in for the meal-planner app.
 *
 * The `basketeer login` CLI refuses to run without a TTY and waits for a
 * manual "Press Enter" after the browser login, so it cannot be driven from
 * the Flask app. This script does the same thing without those gates:
 *
 *   1. Opens a real (headed) Chrome window with basketeer's persistent profile
 *      and the same stealth options (Akamai requires a genuine browser).
 *   2. Loads the Tesco login page.
 *   3. Polls the cookies and, as soon as OAuth.AccessToken appears
 *      (i.e. you signed in), harvests the session via basketeer's own
 *      sessionFromCookies() and writes ~/.basketeer/session.json in the
 *      exact FileTokenStore format (mode 0600).
 *   4. Prints one status line per step (the app tails these into the UI)
 *      and exits 0 on success, 1 on timeout/failure.
 */
import { mkdir, writeFile, chmod } from "node:fs/promises";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { sessionFromCookies } from "basketeer";

const LOGIN_URL = "https://www.tesco.com/account/login";
const HOME_URL = "https://www.tesco.com/groceries/";
const PROFILE_DIR = process.env.BASKETEER_PROFILE_DIR
  ?? join(homedir(), ".basketeer", "chrome-profile");
const SESSION_PATH = process.env.BASKETEER_SESSION_FILE
  ?? join(homedir(), ".basketeer", "session.json");
const TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes to complete the login

// Same stealth shim basketeer uses: make the automation invisible to
// Akamai's bot checks before any page script runs.
const STEALTH_INIT = `() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
}`;

const log = (msg) => console.log(`[tesco-login] ${msg}`);

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  log("ERROR: playwright is not installed. Run: npm install playwright (in the project directory)");
  process.exit(1);
}

const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: "chrome",
  headless: false,
  viewport: { width: 1280, height: 800 },
  locale: "en-GB",
  timezoneId: "Europe/London",
  args: [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
  ],
  ignoreDefaultArgs: ["--enable-automation"],
});

try {
  await ctx.addInitScript(STEALTH_INIT);
  const page = ctx.pages()[0] ?? (await ctx.newPage());

  log("opening Chrome...");
  await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  log("Chrome window opened - sign in to your Tesco account. Waiting for sign-in...");

  const deadline = Date.now() + TIMEOUT_MS;
  let token = null;
  while (Date.now() < deadline) {
    const c = (await ctx.cookies()).find((x) => x.name === "OAuth.AccessToken");
    if (c && c.value) {
      token = c.value;
      break;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }

  if (!token) {
    log("TIMEOUT: no sign-in detected within 10 minutes. Re-run the sign-in and log in in the Chrome window that opens.");
    process.exit(1);
  }

  // Token present: give the page a moment to finish, then re-read (the
  // cookies may rotate one more time during the post-login redirect).
  await new Promise((r) => setTimeout(r, 2000));
  await page.goto(HOME_URL, { waitUntil: "domcontentloaded", timeout: 15_000 }).catch(() => {});
  const session = sessionFromCookies(await ctx.cookies());

  await mkdir(dirname(SESSION_PATH), { recursive: true, mode: 0o700 });
  await writeFile(SESSION_PATH, JSON.stringify(session, null, 2), { mode: 0o600 });
  await chmod(SESSION_PATH, 0o600);

  log(`signed in successfully - session saved to ${SESSION_PATH}`);
  process.exit(0);
} catch (err) {
  log(`ERROR: ${err && err.message ? err.message : err}`);
  process.exit(1);
} finally {
  await ctx.close().catch(() => {});
}
