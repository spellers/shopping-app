#!/usr/bin/env node
/**
 * Standalone Sainsbury's sign-in for the meal-planner app.
 *
 * Mirrors scripts/tesco_login.js: opens a real (headed) Chrome window on the
 * Sainsbury's login page, waits until a WC_AUTHENTICATION_* cookie appears
 * (i.e. the user completed sign-in, including any MFA code), then saves
 * ~/.sainsburys/session.json in the open-supermarkets SessionData format
 * (mode 0600) that the SainsburysProvider loads from.
 *
 * Exits 0 on success, 1 on timeout/failure. Status lines go to stdout.
 */
import { mkdir, writeFile, chmod } from "node:fs/promises";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

const LOGIN_URL = "https://www.sainsburys.co.uk/gol-ui/oauth/login";
const SESSION_PATH = process.env.SAINSBURYS_SESSION_FILE
  ?? join(homedir(), ".sainsburys", "session.json");
const TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes to complete the login

const log = (msg) => console.log(`[sainsburys-login] ${msg}`);

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  log("ERROR: playwright is not installed. Run: npm install playwright (in the project directory)");
  process.exit(1);
}

const ctx = await chromium.launchPersistentContext(
  join(homedir(), ".sainsburys", "chrome-profile"),
  {
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
  },
);

try {
  const page = ctx.pages()[0] ?? (await ctx.newPage());

  log("opening Chrome...");
  await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  log("Chrome window opened - sign in to your Sainsbury's account (enter any MFA code if asked). Waiting for sign-in...");

  const deadline = Date.now() + TIMEOUT_MS;
  let found = null;
  while (Date.now() < deadline) {
    const cookies = await ctx.cookies();
    const auth = cookies.find((c) => c.name.startsWith("WC_AUTHENTICATION_") && c.value);
    if (auth) {
      found = cookies;
      break;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }

  if (!found) {
    log("TIMEOUT: no sign-in detected within 10 minutes. Re-run the sign-in and log in in the Chrome window that opens.");
    process.exit(1);
  }

  // Give the post-login redirect a moment to settle, then re-read so the
  // saved set includes the final cookies.
  await new Promise((r) => setTimeout(r, 2000));
  const cookies = await ctx.cookies();

  const now = new Date();
  const expiresAt = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString();
  const session = {
    cookies,
    expiresAt,
    lastLogin: now.toISOString(),
  };

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
