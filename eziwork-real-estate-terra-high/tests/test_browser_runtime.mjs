import assert from "node:assert/strict";
import { systemBrowserCandidates } from "../scripts/browser_runtime.mjs";


const windows = systemBrowserCandidates("win32", "C:\\Users\\tester");
const mac = systemBrowserCandidates("darwin", "/Users/tester");
const linux = systemBrowserCandidates("linux", "/home/tester");

assert.ok(windows.some((candidate) => candidate.endsWith("chrome.exe")));
assert.ok(windows.some((candidate) => candidate.endsWith("msedge.exe")));
assert.ok(mac.includes("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"));
assert.ok(mac.includes("/Users/tester/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"));
assert.ok(linux.includes("/usr/bin/chromium"));

process.stdout.write("PASS: Windows, macOS, and Linux browser candidates\n");
