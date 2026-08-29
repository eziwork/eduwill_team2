import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";


function readArg(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) {
    throw new Error(`Missing required argument: ${name}`);
  }
  return process.argv[index + 1];
}


function loadPlaywright() {
  const requireCandidates = [
    createRequire(path.resolve(process.cwd(), "package.json")),
    createRequire(import.meta.url),
  ];
  const bundledModules = process.env.CODEX_NODE_MODULES;
  if (bundledModules) {
    requireCandidates.push(createRequire(path.join(bundledModules, "_resolver.cjs")));
  }
  for (const candidate of requireCandidates) {
    try {
      return candidate("playwright");
    } catch {
      // Try the next valid module root.
    }
  }
  throw new Error("Playwright was not found. Run from a workspace with playwright or set CODEX_NODE_MODULES to the bundled node_modules directory.");
}


function findBrowser() {
  const configured = process.env.HTML_PDF_BROWSER;
  const candidates = [
    configured,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}


async function main() {
  const input = path.resolve(readArg("--input"));
  const output = path.resolve(readArg("--output"));
  if (!fs.existsSync(input)) {
    throw new Error(`Input HTML not found: ${input}`);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  if (fs.existsSync(output)) fs.unlinkSync(output);

  const { chromium } = loadPlaywright();
  const executablePath = findBrowser();
  const launchOptions = { headless: true };
  if (executablePath) launchOptions.executablePath = executablePath;

  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
    const releaseStatus = await page.locator('meta[name="derived-release-status"]').getAttribute("content");
    if (!releaseStatus || releaseStatus === "HOLD") {
      throw new Error(`PDF rendering refused for release status: ${releaseStatus || "MISSING"}`);
    }
    await page.waitForFunction(
      () => [...document.images].every((image) => image.complete && image.naturalWidth > 0),
      null,
      { timeout: 15000 },
    );
    const plotCount = await page.locator(".plot").count();
    if (plotCount > 0) {
      await page.waitForFunction(() => window.__REPORT_CHARTS_READY__ === true, null, { timeout: 15000 });
      await page.waitForFunction(
        (expected) => document.querySelectorAll(".plot svg").length === expected,
        plotCount,
        { timeout: 15000 },
      );
    }
    if (consoleErrors.length || pageErrors.length) {
      throw new Error(`Browser errors: ${[...pageErrors, ...consoleErrors].join(" | ")}`);
    }
    await page.emulateMedia({ media: "print" });
    await page.pdf({
      path: output,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: "0", right: "0", bottom: "0", left: "0" },
    });
    process.stdout.write(`${output}\n`);
  } finally {
    await browser.close();
  }
}


main().catch((error) => {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exitCode = 3;
});
