import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { resolveChromiumRuntime } from "./browser_runtime.mjs";


function readArg(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) throw new Error(`Missing required argument: ${name}`);
  return process.argv[index + 1];
}


async function main() {
  const input = path.resolve(readArg("--input"));
  const outputDir = path.resolve(readArg("--output-dir"));
  if (!fs.existsSync(input)) throw new Error(`Input HTML not found: ${input}`);
  fs.mkdirSync(outputDir, { recursive: true });

  const { chromium, launchOptions } = resolveChromiumRuntime();
  const browser = await chromium.launch(launchOptions);
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
