import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";


export function loadPlaywright() {
  const requireCandidates = [
    createRequire(path.resolve(process.cwd(), "package.json")),
    createRequire(import.meta.url),
  ];
  if (process.env.CODEX_NODE_MODULES) {
    requireCandidates.push(createRequire(path.join(process.env.CODEX_NODE_MODULES, "_resolver.cjs")));
  }
  for (const candidate of requireCandidates) {
    try {
      return candidate("playwright");
    } catch {
      // Try the next valid module root.
    }
  }
  throw new Error("Playwright was not found. Install playwright or set CODEX_NODE_MODULES to the bundled node_modules directory.");
}


export function systemBrowserCandidates(platform = process.platform, homeDir = os.homedir()) {
  if (platform === "win32") {
    return [
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
      "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ];
  }
  if (platform === "darwin") {
    return [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      path.posix.join(homeDir, "Applications", "Google Chrome.app", "Contents", "MacOS", "Google Chrome"),
      path.posix.join(homeDir, "Applications", "Microsoft Edge.app", "Contents", "MacOS", "Microsoft Edge"),
    ];
  }
  return [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
  ];
}


export function resolveChromiumRuntime() {
  const { chromium } = loadPlaywright();
  const configured = process.env.HTML_PDF_BROWSER;
  if (configured) {
    const resolved = path.resolve(configured);
    if (!fs.existsSync(resolved)) throw new Error(`HTML_PDF_BROWSER was not found: ${resolved}`);
    return { chromium, launchOptions: { headless: true, executablePath: resolved }, browserPath: resolved, source: "configured" };
  }

  const bundledPath = chromium.executablePath();
  if (bundledPath && fs.existsSync(bundledPath)) {
    return { chromium, launchOptions: { headless: true }, browserPath: bundledPath, source: "playwright-bundled" };
  }

  const systemPath = systemBrowserCandidates().find((candidate) => fs.existsSync(candidate));
  if (systemPath) {
    return { chromium, launchOptions: { headless: true, executablePath: systemPath }, browserPath: systemPath, source: "system" };
  }
  throw new Error(`No Chromium browser was found for ${process.platform}. Install Playwright Chromium or set HTML_PDF_BROWSER.`);
}
