import { resolveChromiumRuntime } from "./browser_runtime.mjs";


try {
  const runtime = resolveChromiumRuntime();
  process.stdout.write(`${JSON.stringify({
    ready: true,
    platform: process.platform,
    browser_path: runtime.browserPath,
    browser_source: runtime.source,
  })}\n`);
} catch (error) {
  process.stdout.write(`${JSON.stringify({
    ready: false,
    platform: process.platform,
    error: error.message,
  })}\n`);
  process.exitCode = 2;
}
