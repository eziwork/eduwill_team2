# Customer report writing and design

## Choose the communication mode

- Use `CUSTOMER_SALES` when the user is a broker or agent and the report will be shown to a prospective customer. Read [customer-sales-copy.md](customer-sales-copy.md). Its job is to create informed interest, earn an on-site visit, and continue into consultation.
- Use `BUYER_ADVISORY` only when the user explicitly asks for independent purchase-risk analysis, negotiation anchors, a walk-away condition, or an internal broker memo.
- Do not mix the modes in one customer-facing report. In particular, do not place internal offer prices, ceilings, or deal-killing verdicts inside a sales handout.

## Canonical report profile

- Use the **Golden V3 nine-page profile** for every standard report: buyer, seller, tenant, landlord, apartment, land, commercial, sale, jeonse, and monthly rent.
- The property and question determine the page content, chart units, and role-specific call to action. They do not select another renderer or visual system.
- Legacy `COMPACT_6` intake is accepted only as an alias and must normalize to `EXTENDED_9` before build.
- When evidence is unavailable, retain the page purpose with a designed evidence-status or value-confirmation component. Never replace the page with a sparse generic matrix or invent a fact to fill it.

## Broker brand assets

- Confirm `output.brand_name` and `output.logo_path` before generating a customer report. Ask for the office name and logo image together when either is missing.
- Accept PNG, JPG, JPEG, WEBP, or SVG logos up to 5 MB. A relative path is resolved from the intake file and copied into the report package.
- Display the logo and office name as one brand lockup on the cover and in every page footer. Preserve the logo's aspect ratio and embed it in the standalone HTML/PDF.
- Treat the logo as a packaged asset: hash it in the evidence audit and fail the build if the staged file is missing.

Every page starts with one useful takeaway. In `CUSTOMER_SALES`, lead with a verified attraction, fit, or reason to inspect the property and turn uncertainty into a value-confirmation point. In `BUYER_ADVISORY`, lead with the decision answer. Use calm Korean such as `확인됩니다`, `비교할 수 있습니다`, and `현장에서 확인하면 가치 판단이 더 구체화됩니다`. Do not expose internal process phrases or imply certainty.

Time-sensitive facts include a source and basis date. Explain unfamiliar terms once. Generate repeated numbers from the same normalized field.

## Build commands

The wrapper is the only supported entrypoint for demo or actual packages:

```powershell
pwsh -NoProfile -File scripts/run_report.ps1 `
  -IntakePath path\to\intake.json `
  -ReportRoot path\to\reports\report-id `
  -OfficialRowsPath path\to\rtms_target_rows.json `
  -OfficialManifestPath path\to\collection_manifest.json `
  -ListingsPath path\to\listings.json
```

Individual commands are:

```powershell
python scripts/prepare_report.py --intake intake.json --report-root report-root [evidence options]
python scripts/audit_evidence.py report-root\report-request.json --output report-root\evidence-audit.json
python scripts/build_report.py report-root\report-request.json --output report-root\report.html --audit-output report-root\evidence-audit.json
python scripts/validate_report.py report-root\report.html --request report-root\report-request.json
node scripts/render_report.mjs --input report-root\report.html --output report-root\report.pdf
python scripts/validate_pdf.py report-root\report.pdf --request report-root\report-request.json --html report-root\report.html
```

`build_report.py` always delegates standard reports to `EZIWORK_GOLDEN_V3`; no standalone or report-specific builder is allowed. `HOLD` stops before customer HTML/PDF. `PASS WITH CONDITIONS` may be rendered only when every sample or partial limitation remains visible.

## Visual QA

Use A4 portrait, EZIWORK blue `#2c61ef`, dark blue `#153f9d`, coral `#ef6a4a`, large question titles, one useful visual per evidence page, and generous whitespace.

After rendering, inspect every page image for Korean text clipping, chart overflow, blank pages, incorrect units/signs, missing sources, broken local images, footer collision, and missing demo badges. Verify the final page count against the selected profile instead of shrinking typography to force a count.
