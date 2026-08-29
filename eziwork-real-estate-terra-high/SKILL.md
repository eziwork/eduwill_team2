---
name: eziwork-real-estate-terra-high
description: Create and visually quality-gate nine-page EZIWORK Korean real-estate reports in a GPT-5.6 Terra high-reasoning workflow. Use only when explicitly requested for Terra High production, buyer-advisory negotiation analysis, or reference-PDF-calibrated visual QA; preserve the baseline eziwork-real-estate-market-brief skill unchanged.
---

# EZIWORK Real Estate Terra High

Create one sourced, nine-page HTML/PDF report with the `EZIWORK_GOLDEN_V3` renderer and the `TERRA_HIGH_100` quality profile. This skill is a separate experimental production lane. Never edit, replace, or install over `eziwork-real-estate-market-brief`.

This skill is designed for a task already configured to `gpt-5.6-terra` with `high` reasoning. Local skill metadata cannot switch or enforce a model. If the active task model/effort is not visible, record `runtime_model_verified=false` in the QA result instead of claiming enforcement. The report pipeline remains deterministic regardless of that runtime label.

## Route the request

1. Read [references/intake-and-routing.md](references/intake-and-routing.md) and normalize the request to intake v1.0. For a real customer report, require `output.brand_name` and `output.logo_path`.
2. Run `pwsh -NoProfile -File scripts/preflight_system.ps1 -Format Json` once. Use [references/platform-compatibility.md](references/platform-compatibility.md) only for setup failures.
3. Run `scripts/validate_intake.py` and `scripts/plan_sources.py`. For actual official data, use only the registered routes in [references/collection-and-evidence.md](references/collection-and-evidence.md).
4. Read [references/analysis-and-matching.md](references/analysis-and-matching.md) before calculating or matching. Keep completed transactions, current asking prices, user facts, and interpretation separate.
5. Select exactly one communication mode:
   - `CUSTOMER_SALES`: broker-to-customer explanation that leads to an on-site consultation. Do not expose negotiation anchors, a buyer ceiling, or “즉시 계약 보류”. Read [references/customer-sales-copy.md](references/customer-sales-copy.md).
   - `BUYER_ADVISORY`: use only when the user explicitly requests independent buy-side risk or negotiation advice. Read [references/extended-buyer-decision-report.md](references/extended-buyer-decision-report.md). Numeric offer/ceiling/break-even advice must come from user-provided fields or a traceable dated calculation; otherwise show `추가 산정 필요`.
6. Read [references/report-writing-and-design.md](references/report-writing-and-design.md), [references/customer-sales-golden-v3.md](references/customer-sales-golden-v3.md), and [references/terra-high-quality-contract.md](references/terra-high-quality-contract.md) before writing.
7. Run only `scripts/run_report.ps1`. It prepares, audits, builds, inspects layout, renders, validates, captures every page, and runs the 100-point visual gate. Pass `-ReferencePdf` when a user supplies a reference PDF.
8. Inspect all nine page PNGs with image vision. Repair the source and rerun until the automated score is `100`, all hard gates pass, and visual inspection finds no clipping, overlap, sparse accidental whitespace, broken image, or unreadable chart.

## Terra High quality contract

- Fixed A4, exactly nine pages, page labels `01 / 09` through `09 / 09`.
- Dark navy cover and final page; light editorial pages 2–8.
- Palette anchors: navy `#082f58`, blue `#0a67ff`, orange `#f37021`, pale blue surfaces, white cards.
- One dominant visual or evidence structure per analytical page; three KPI cards where the page hierarchy calls for them.
- HTML metadata includes `report-quality-profile=TERRA_HIGH_100`, version `1.0.0`, recommended model `gpt-5.6-terra`, and recommended reasoning `high`.
- `layout-inspection.json` has zero overflow, clipping, collision, missing-image, and unexpected-page findings.
- `visual-quality.json` scores `100/100`. This means every declared deterministic gate passed; it is not a claim that an aesthetic judgment is mathematically universal.
- When a reference PDF is supplied, report exact pixel equality separately from perceptual similarity. Never label a non-identical render as pixel-identical.

## Non-negotiable evidence boundaries

- Never invent a price, count, trend, rate, source, listing, condition, permission, or recommendation input.
- Never merge completed transaction prices and current asking prices into one synthetic market price.
- Preserve cancelled transactions in raw evidence and exclude them from aggregates.
- Treat the current reporting month as provisional.
- Keep monthly-rent deposit and rent separate unless a dated conversion rule and source are supplied.
- A browser sample is a checked sample, not complete inventory. Stop on CAPTCHA, blocking, re-authentication, uncertain identity, or repeated failure.
- `demo` values display `교육용 예시 · 실제 시세가 아님` on every page.
- `HOLD` blocks customer HTML/PDF output. Do not bypass the audit.
- The report is a consultation aid, not an appraisal, legal/tax opinion, permit, loan/guarantee decision, or price promise.

## Completion

Return the HTML, PDF, evidence audit, `layout-inspection.json`, `visual-quality.json`, and nine review images. State the target, basis date, evidence mode, communication mode, release result, quality score, reference comparison result, missing sources, runtime-model verification state, and remaining field checks.

Read [references/extension-guide.md](references/extension-guide.md) only when adding a source, property route, metric, matching rule, or report section.
