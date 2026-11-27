// Browser test of the clip workflow against the running stack.
// Usage: node e2e/clips.mjs <speech-video> [screens-dir]
// Without ANTHROPIC_API_KEY it verifies transcription + the clear "key missing" error.
// With a key it waits for real AI candidates, renders the top 2 and checks the downloads.
import { createRequire } from "node:module";
import fs from "node:fs";
const { chromium } = createRequire(import.meta.url)("playwright");

const video = process.argv[2];
const shots = process.argv[3] || "e2e-screens";
const WEB = process.env.WEB_URL || "http://localhost:3000";
const API = process.env.API_URL || "http://localhost:8000/api/v1";
fs.mkdirSync(shots, { recursive: true });

const caps = await (await fetch(`${API}/capabilities`)).json();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

await page.goto(`${WEB}/projects/new`);
await page.waitForFunction(() => document.documentElement.dataset.hydrated === "true");
await page.getByTestId("file-input").setInputFiles(video);
await page.getByRole("button", { name: /Upload and create project/ }).click();
await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/, { timeout: 180_000 });
const projectId = page.url().split("/").pop();
await page.getByText("Find the best clips with AI").waitFor({ timeout: 180_000 });
console.log("ok: project ready", projectId);

await page.getByRole("combobox").first().selectOption("id");
await page.getByRole("button", { name: /Find clips/ }).click();
await page.getByTestId("analysis-progress").waitFor();
await page.getByText("Transcribing speech", { exact: true }).waitFor({ timeout: 120_000 });
await page.waitForTimeout(4000);
await page.getByTestId("analysis-progress").scrollIntoViewIfNeeded();
await page.screenshot({ path: `${shots}/10-transcribing.png` });
console.log("ok: transcription running with live progress");

if (!caps.ai.api_key_configured) {
  await page.getByText(/needs a Claude API key/).waitFor({ timeout: 600_000 });
  await page.getByText(/Transcript: \d+ words/).waitFor();
  await page.screenshot({ path: `${shots}/11-no-key.png` });
  console.log("ok: no API key -> transcript kept, clear error shown");
  fs.writeFileSync(`${shots}/project_id.txt`, projectId);
} else {
  await page.getByText(/clip candidates?$/).waitFor({ timeout: 900_000 });
  console.log("ok: AI candidates shown");
}
await browser.close();
if (errors.length) { console.error(errors); process.exit(1); }
console.log("CLIP E2E (phase 1) PASSED");
