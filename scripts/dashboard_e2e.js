// Dashboard end-to-end (Playwright). Needs API on :8000 (ADMIN_TOKEN) and dashboard on :3000.
// Usage: ADMIN_TOKEN=adm node scripts/dashboard_e2e.js [screenshot_dir]
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const API = process.env.GUARD_URL || "http://localhost:8000", DASH = process.env.DASH_URL || "http://localhost:3000", ADMIN = process.env.ADMIN_TOKEN || "adm";
const shots = process.argv[2];
const j = (path, key, method = "GET", body) => fetch(API + path, { method, headers: { "Content-Type": "application/json", Authorization: "Bearer " + key }, body: body && JSON.stringify(body) }).then((r) => r.json());
(async () => {
  const id = "dash_" + Math.random().toString(36).slice(2, 8);
  const { api_key: key } = await (await fetch(API + "/admin/tenants", { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": ADMIN }, body: JSON.stringify({ id, name: id }) })).json();
  const pid = (await j(`/v1/guard`, key, "POST", { message: "hi", user_id: "919876543210" })).principal;
  await j("/v1/guard", key, "POST", { message: "1", user_id: "919876543210" });
  await j("/v1/guard", key, "POST", { message: "meri details hatao", user_id: "919876543210" });
  await j("/v1/breaches", key, "POST", { title: "Public Google Sheet", description: "link was public" });
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1100, height: 800 } }); const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  p.on("console", (m) => m.type() === "error" && !/401/.test(m.text()) && errs.push(m.text()));
  const text = async () => (await p.innerText("main")).replace(/\n+/g, " | ");
  const shot = async (n) => shots && (await p.screenshot({ path: `${shots}/${n}.png`, fullPage: true }));

  // 1. unauthenticated: no data, clear message, wrong key rejected
  await p.goto(DASH + "/rights"); await p.waitForTimeout(800);
  assert.match(await text(), /Not logged in/); 
  await p.goto(DASH + "/"); await p.fill("input[type=password]", "dg_wrong"); await p.click("button:has-text('Log in')"); await p.waitForTimeout(800);
  assert.match(await text(), /Invalid API key/);

  // 2. login: key must be an httpOnly cookie and unreachable from page JS
  await p.fill("input[type=password]", key); await p.click("button:has-text('Log in')"); await p.waitForSelector("text=Logged in");
  const cookie = (await ctx.cookies()).find((c) => c.name === "dg_session");
  assert.ok(cookie && cookie.httpOnly && cookie.sameSite === "Strict", "session cookie must be httpOnly + SameSite=Strict");
  assert.equal(await p.evaluate(() => document.cookie.includes("dg_session")), false);
  assert.equal(await p.evaluate(() => JSON.stringify({ ...localStorage })).then((s) => s.includes("dg_")), false, "no key in localStorage");
  await p.waitForTimeout(1200); await shot("overview");
  assert.match(await text(), /Verified/);

  // 3. data pages
  await p.goto(DASH + "/rights"); await p.waitForTimeout(1000); assert.match(await text(), /erasure/); await shot("rights");
  await p.click("text=Approve & erase"); await p.waitForTimeout(800); assert.match(await text(), /Queued R-/);
  await p.goto(DASH + "/erasure"); await p.waitForTimeout(800); await p.click("text=Run workers now"); await p.waitForTimeout(1200);
  assert.match(await text(), /done/); await shot("erasure");
  await p.goto(DASH + "/consents"); await p.waitForTimeout(800); assert.match(await text(), /order_updates/);
  await p.goto(DASH + "/breaches"); await p.waitForTimeout(800); assert.match(await text(), /Public Google Sheet/); assert.match(await text(), /h left/); await shot("breaches");

  // 4. connectors: add, secrets not echoed, remove
  await p.goto(DASH + "/connectors"); await p.waitForTimeout(600);
  await p.fill("input[placeholder=Name]", "crm"); await p.fill("textarea", '{"url":"http://x","secret":"TOPSECRET"}'); await p.click("text=Add connector"); await p.waitForTimeout(800);
  let t = await text(); assert.match(t, /crm/); assert.ok(!t.includes("TOPSECRET")); await shot("connectors");
  await p.click("text=Remove"); await p.waitForTimeout(600); assert.ok(!(await text()).includes("crm |"));
  // unverified connector warning
  await p.selectOption("select", "hubspot"); assert.match(await text(), /untested/);

  // 5. principal lookup (phone -> hash -> export)
  await p.goto(DASH + "/lookup"); await p.fill("input", "+91 98765 43210"); await p.click("text=Look up"); await p.waitForTimeout(1200);
  t = await text(); assert.ok(t.includes(pid), "lookup must resolve to the same principal hash the guard used"); assert.match(t, /order_updates/); await shot("lookup");

  // 6. notices page flags draft status
  await p.goto(DASH + "/notices"); await p.waitForTimeout(800); assert.match(await text(), /lawyer review required/); await shot("notices");

  // 7. public checker works and audit pack downloads
  await p.goto(DASH + "/checker"); await p.fill("textarea", "Bot: By continuing you agree to our terms. phone?\nUser: 9876543210"); await p.click("button:has-text('Check')"); await p.waitForTimeout(1000);
  assert.match(await text(), /\/100/); await shot("checker");
  await p.goto(DASH + "/audit"); const [d] = await Promise.all([p.waitForEvent("download"), p.click("text=Download")]); assert.equal(d.suggestedFilename(), "audit-pack.zip");

  // 8. logout clears the session
  await p.goto(DASH + "/"); await p.waitForSelector("text=Logged in"); await p.click("text=Log out"); await p.waitForSelector("input[type=password]");
  await p.goto(DASH + "/rights"); await p.waitForTimeout(800); assert.match(await text(), /Not logged in/);

  // 8b. public landing page: no dashboard nav, consent gating, per-purpose storage, delete link works
  const pub = await b.newContext(); const q = await pub.newPage();
  await q.goto(DASH + "/welcome"); await q.waitForTimeout(800);
  assert.equal(await q.locator("nav").count(), 0, "public page must not show dashboard nav");
  const em = `lead_${id}@example.com`;
  await q.fill("input[type=email]", em);
  assert.equal(await q.locator("button:has-text('Join waitlist')").isDisabled(), true, "cannot join without the required consent");
  await q.check("text=Also send me occasional"); assert.equal(await q.locator("button:has-text('Join waitlist')").isDisabled(), true, "optional consent alone is not enough");
  await q.check("text=Contact me about DPDP Guard"); await q.click("button:has-text('Join waitlist')"); await q.waitForSelector("text=You're on the list");
  const body = await q.innerText("body"); assert.match(body, /launch_contact, tips/); assert.match(body, /365 days/);
  if (shots) await q.screenshot({ path: `${shots}/welcome.png`, fullPage: true });
  const wl = await (await fetch(API + "/admin/waitlist", { headers: { "X-Admin-Token": ADMIN } })).json(); assert.ok(wl.some((r) => r.email === em), "signup stored");
  const link = await q.locator("a[href*='delete=']").first().getAttribute("href");
  await q.goto(DASH + link); await q.click("text=Yes, delete it"); await q.waitForSelector("text=your signup was deleted");
  const wl2 = await (await fetch(API + "/admin/waitlist", { headers: { "X-Admin-Token": ADMIN } })).json(); assert.ok(!wl2.some((r) => r.email === em), "signup erased via delete link");
  await pub.close();

  // 9. cross-origin state change is refused by the proxy
  const bad = await fetch(DASH + "/api/guard/v1/connectors", { method: "POST", headers: { "Content-Type": "application/json", Origin: "http://evil.example" }, body: "{}" });
  assert.equal(bad.status, 403);

  assert.deepEqual(errs, [], "browser errors: " + errs.join("; "));
  await b.close(); console.log("dashboard e2e OK");
})().catch((e) => { console.error("DASHBOARD E2E FAILED:", e.message); process.exit(1); });
