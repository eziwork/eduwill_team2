import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";


function readArg(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) throw new Error(`Missing required argument: ${name}`);
  return process.argv[index + 1];
}


function loadPlaywright() {
  const candidates = [createRequire(path.resolve(process.cwd(), "package.json")), createRequire(import.meta.url)];
  if (process.env.CODEX_NODE_MODULES) {
    candidates.push(createRequire(path.join(process.env.CODEX_NODE_MODULES, "_resolver.cjs")));
  }
  for (const candidate of candidates) {
    try {
      return candidate("playwright");
    } catch {
      // Continue to the next module root.
    }
  }
  throw new Error("Playwright was not found. Set CODEX_NODE_MODULES or install playwright in the workspace.");
}


function findBrowser() {
  return [
    process.env.HTML_PDF_BROWSER,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean).find((candidate) => fs.existsSync(candidate));
}


async function main() {
  const input = path.resolve(readArg("--input"));
  const outputDir = path.resolve(readArg("--output-dir"));
  if (!fs.existsSync(input)) throw new Error(`Input HTML not found: ${input}`);
  fs.mkdirSync(outputDir, { recursive: true });

  const { chromium } = loadPlaywright();
  const executablePath = findBrowser();
  const browser = await chromium.launch(executablePath ? { headless: true, executablePath } : { headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1188, height: 1680 }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
    await page.waitForFunction(() => [...document.images].every((image) => image.complete && image.naturalWidth > 0));
    const engine = await page.locator('meta[name="report-engine"]').getAttribute("content");
    const version = await page.locator('meta[name="report-engine-version"]').getAttribute("content");
    if (engine !== "EZIWORK_GOLDEN_V3" || version !== "3.1.0") {
      throw new Error(`Unexpected report engine: ${engine || "missing"} ${version || "missing"}`);
    }
    const sheets = page.locator(".sheet");
    const count = await sheets.count();
    if (count !== 9) throw new Error(`Expected nine Golden V3 pages, found ${count}`);
    for (let index = 0; index < count; index += 1) {
      const target = path.join(outputDir, `page-${String(index + 1).padStart(2, "0")}.png`);
      await sheets.nth(index).screenshot({ path: target, animations: "disabled" });
    }
    process.stdout.write(`${outputDir}\n`);
  } finally {
    await browser.close();
  }
}


main().catch((error) => {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exitCode = 3;
});
