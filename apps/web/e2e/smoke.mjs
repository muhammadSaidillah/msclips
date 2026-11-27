// End-to-end smoke test against running web (3000) + API (8000) + worker.
// Usage: node e2e/smoke.mjs <video-file> [screenshot-dir]
import { createRequire } from "node:module";
import path from "node:path";
import fs from "node:fs";

// Resolve playwright from the project or a global install (NODE_PATH).
const { chromium } = createRequire(import.meta.url)("playwright");

const video = process.argv[2];
const shots = process.argv[3] || "e2e-screens";
const WEB = process.env.WEB_URL || "http://localhost:3000";
if (!video) throw new Error("pass a video file");
fs.mkdirSync(shots, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
const open = async (p, url) => {
  await p.goto(url);
  await p.waitForFunction(() => document.documentElement.dataset.hydrated === "true");
};
page.on("pageerror", (e) => errors.push(e.message));

// 1. invalid file is rejected client-side
await open(page, `${WEB}/projects/new`);
const bad = path.join(path.dirname(video), "notes.txt");
fs.writeFileSync(bad, "not a video");
await page.getByTestId("file-input").setInputFiles(bad);
await page.getByText("is not a supported video file").waitFor();
console.log("ok: invalid file rejected");

// 2. real upload with progress
await page.getByTestId("file-input").setInputFiles(video);
await page.getByRole("button", { name: /Upload and create project/ }).click();
await page.getByTestId("upload-progress").waitFor();
await page.waitForTimeout(400);
await page.screenshot({ path: `${shots}/02-uploading.png` });
await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/, { timeout: 120_000 });
console.log("ok: upload confirmed, redirected to", page.url());

// 3. worker extracts metadata; page shows summary when ready
await page.getByText("Video summary").waitFor({ timeout: 120_000 });
await page.getByText("1920×1080").first().waitFor();
await page.waitForTimeout(800);
await page.screenshot({ path: `${shots}/03-project-ready.png`, fullPage: true });
console.log("ok: metadata visible");

// 4. dashboard + list reflect the project
await page.goto(`${WEB}/`);
await page.getByText("Recent projects").waitFor();
await page.waitForTimeout(500);
await page.screenshot({ path: `${shots}/01-dashboard.png` });
await page.goto(`${WEB}/projects`);
await page.waitForTimeout(800);
await page.screenshot({ path: `${shots}/04-projects.png` });

// 5. cancel mid-upload (throttle chunks so we can cancel)
await open(page, `${WEB}/projects/new`);
await page.route("**/api/v1/uploads/*/chunks/*", async (r) => {
  await new Promise((res) => setTimeout(res, 1500));
  await r.continue().catch(() => {});
});
await page.getByTestId("file-input").setInputFiles(video);
await page.getByRole("button", { name: /Upload and create project/ }).click();
await page.getByRole("button", { name: /Cancel upload/ }).click();
await page.getByText("Upload cancelled").waitFor();
console.log("ok: cancel works");
await page.unroute("**/api/v1/uploads/*/chunks/*");

// 6. network failure mid-upload -> resume
await open(page, `${WEB}/projects/new`);
let failing = false;
let sent = 0;
await page.route("**/api/v1/uploads/*/chunks/*", async (r) => {
  sent++;
  if (sent > 2) failing = true;
  if (failing) return r.abort("failed");
  return r.continue();
});
await page.getByTestId("file-input").setInputFiles(video);
await page.getByRole("button", { name: /Upload and create project/ }).click();
await page.getByText("Upload interrupted").waitFor({ timeout: 90_000 });
await page.screenshot({ path: `${shots}/05-interrupted.png` });
await page.unroute("**/api/v1/uploads/*/chunks/*");
await page.getByRole("button", { name: /Resume upload/ }).click();
await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/, { timeout: 120_000 });
await page.getByText("Video summary").waitFor({ timeout: 120_000 });
console.log("ok: resume after network failure");

// 7. mobile layout
const m = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await m.goto(page.url());
await m.getByText("Video summary").waitFor();
await m.waitForTimeout(500);
await m.screenshot({ path: `${shots}/06-mobile-project.png`, fullPage: true });

await browser.close();
if (errors.length) {
  console.error("page errors:", errors);
  process.exit(1);
}
console.log("ALL E2E CHECKS PASSED");
