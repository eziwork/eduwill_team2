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
  const output = path.resolve(readArg("--output"));
  if (!fs.existsSync(input)) throw new Error(`Input HTML not found: ${input}`);
  fs.mkdirSync(path.dirname(output), { recursive: true });

  const { chromium, launchOptions } = resolveChromiumRuntime();
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
    const browserErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => [...document.images].every((image) => image.complete), null, { timeout: 15000 });
    if (await page.locator(".plot").count()) {
      await page.waitForFunction(() => window.__REPORT_CHARTS_READY__ === true, null, { timeout: 15000 });
    }

    const report = await page.evaluate(() => {
      const sheets = [...document.querySelectorAll(".sheet")];
      const brokenImages = [...document.images]
        .filter((image) => !image.complete || image.naturalWidth < 1 || image.naturalHeight < 1)
        .map((image) => image.getAttribute("src") || "missing-src");
      const overflows = [];
      const outOfBounds = [];
      const footerCollisions = [];
      const sheetMetrics = [];

      sheets.forEach((sheet, pageIndex) => {
        const pageNumber = pageIndex + 1;
        const box = sheet.getBoundingClientRect();
        const scrollOverflowX = Math.max(0, sheet.scrollWidth - sheet.clientWidth);
        const scrollOverflowY = Math.max(0, sheet.scrollHeight - sheet.clientHeight);
        if (scrollOverflowX > 2 || scrollOverflowY > 2) {
          overflows.push({ page: pageNumber, selector: ".sheet", x: scrollOverflowX, y: scrollOverflowY });
        }
        const elements = [...sheet.querySelectorAll("*")];
        elements.forEach((element) => {
          if (!(element instanceof HTMLElement || element instanceof SVGElement)) return;
          const style = getComputedStyle(element);
          if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return;
          const rect = element.getBoundingClientRect();
          if (rect.width < 1 || rect.height < 1) return;
          const selector = `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${element.classList.length ? `.${[...element.classList].slice(0, 3).join(".")}` : ""}`;
          const outside = rect.left < box.left - 2 || rect.right > box.right + 2 || rect.top < box.top - 2 || rect.bottom > box.bottom + 2;
          if (outside) {
            outOfBounds.push({ page: pageNumber, selector, rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom } });
          }
          if (element instanceof HTMLElement && element.clientWidth > 8 && element.clientHeight > 8) {
            const x = Math.max(0, element.scrollWidth - element.clientWidth);
            const y = Math.max(0, element.scrollHeight - element.clientHeight);
            const typographicTag = ["H1", "H2", "H3", "H4", "P", "B", "STRONG", "SPAN", "SMALL", "TD", "TH"].includes(element.tagName);
            if (!typographicTag && (x > 12 || y > 12) && style.overflowX !== "auto" && style.overflowY !== "auto") {
              overflows.push({ page: pageNumber, selector, x, y });
            }
          }
        });

        const footerTop = box.bottom - 42;
        [...sheet.children].forEach((element) => {
          if (element.matches(".brand,.page-no,.cover-photo,.cover-gradient,.demo-badge,script,style")) return;
          const rect = element.getBoundingClientRect();
          if (rect.height > 1 && rect.bottom > footerTop) {
            footerCollisions.push({ page: pageNumber, selector: element.className || element.tagName, bottom: rect.bottom, footerTop });
          }
        });
        sheetMetrics.push({
          page: pageNumber,
          width: Number(box.width.toFixed(2)),
          height: Number(box.height.toFixed(2)),
          background: getComputedStyle(sheet).backgroundColor,
          textCharacters: (sheet.innerText || "").replace(/\s+/g, "").length,
        });
      });

      const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
      return {
        engine: meta("report-engine"),
        engine_version: meta("report-engine-version"),
        quality_profile: meta("report-quality-profile"),
        quality_profile_version: meta("report-quality-profile-version"),
        sheet_count: sheets.length,
        broken_images: brokenImages,
        overflows,
        out_of_bounds: outOfBounds,
        footer_collisions: footerCollisions,
        sheet_metrics: sheetMetrics,
      };
    });

    const errors = [...browserErrors];
    if (report.engine !== "EZIWORK_GOLDEN_V3" || report.engine_version !== "3.1.0") errors.push("unexpected report engine metadata");
    if (report.quality_profile !== "TERRA_HIGH_100" || report.quality_profile_version !== "1.0.0") errors.push("unexpected Terra High quality metadata");
    if (report.sheet_count !== 9) errors.push(`expected 9 sheets, found ${report.sheet_count}`);
    if (report.broken_images.length) errors.push(`${report.broken_images.length} broken image(s)`);
    if (report.overflows.length) errors.push(`${report.overflows.length} overflow finding(s)`);
    if (report.out_of_bounds.length) errors.push(`${report.out_of_bounds.length} out-of-bounds finding(s)`);
    if (report.footer_collisions.length) errors.push(`${report.footer_collisions.length} footer collision(s)`);
    report.errors = errors;
    report.status = errors.length ? "FAIL" : "PASS";
    fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    process.stdout.write(`${report.status}: ${output}\n`);
    if (errors.length) process.exitCode = 2;
  } finally {
    await browser.close();
  }
}


main().catch((error) => {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exitCode = 3;
});
