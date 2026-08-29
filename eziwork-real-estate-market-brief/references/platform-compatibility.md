# Windows and macOS runtime support

The canonical entrypoints are PowerShell 7 scripts on both platforms. Run preflight before collection or report generation:

```powershell
pwsh -NoProfile -File scripts/preflight_system.ps1 -Format Json
```

## Runtime resolution

The scripts resolve Python as `python`/`python3`, Node.js as `node`, then check the Codex bundled dependency runtime. Explicit command names or paths remain available:

```powershell
pwsh -NoProfile -File scripts/run_report.ps1 `
  -IntakePath intake.json `
  -ReportRoot report `
  -PythonExe python3 `
  -NodeExe node
```

`-SkipPdf` does not require Node.js, Playwright, or a browser. A complete HTML/PDF package requires the Playwright module and either its bundled Chromium or a supported system browser. Set `HTML_PDF_BROWSER` to an explicit executable when automatic discovery is unsuitable.

On macOS the renderer checks Playwright Chromium, `/Applications/Google Chrome.app`, Microsoft Edge, Chromium, and the same applications under `~/Applications`. If Playwright is installed without its browser, install Chromium through the Playwright package available in the environment.

## Credentials

- Windows: `save_provider_api_key.ps1` uses current-user DPAPI.
- macOS: the same script uses the current user's login Keychain through `/usr/bin/security`.
- Other platforms: use the provider environment variable; no plaintext credential file is created.

Do not copy a Windows `.dpapi` credential file to macOS. Use the save script again on the Mac or set `DATA_GO_KR_SERVICE_KEY` for the current process.

## Verification

Run the Python suite, PowerShell route tests, platform-path tests, browser-candidate tests, and one full demo report. macOS release verification still requires visual inspection of all nine rendered PNG pages because installed Korean fonts can change line wrapping.
