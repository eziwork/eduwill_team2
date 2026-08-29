---
name: eziwork-real-estate-market-brief
description: Create sourced Korean real-estate market briefs and broker customer-sales reports from structured intake, official MOLIT transactions, and limited public-listing or user-provided evidence. Use customer-sales copy for broker handouts and analytical copy for explicitly requested independent buyer advice; do not use as an appraisal, legal determination, or unrestricted listing crawler.
---

# EZIWORK Real Estate Market Brief

Create one customer-readable HTML/PDF brief. When a broker or agent is preparing material for a prospective customer, default to `CUSTOMER_SALES`: help the customer understand the property's appeal, see why an on-site visit is worthwhile, and continue into consultation without inventing or concealing material facts. Use `BUYER_ADVISORY` only when the user explicitly asks for independent buy-side risk or negotiation advice. Every standard report uses the canonical `EZIWORK_GOLDEN_V3` nine-page engine; the question changes the evidence and copy, never the design system or renderer. Keep official transactions, current public listings, user-provided facts, and interpretations separate from intake through delivery.

## Route the request

1. Read [references/intake-and-routing.md](references/intake-and-routing.md) and normalize the request to `intake v1.0`. Before generating any customer HTML/PDF, confirm the real-estate office name (`output.brand_name`) and obtain its logo image (`output.logo_path`). If either is missing, ask for both in one concise question; do not silently substitute `EZIWORK` for an actual report. Ask only for other missing fields that change the source, comparison scope, or customer decision.
2. Run `pwsh -NoProfile -File scripts/preflight_system.ps1 -Format Json` once. The same entrypoint supports Windows and macOS. Intake and `demo` reports may continue without credentials; an `actual` official-data route may not collect until its credential is usable. Read [references/platform-compatibility.md](references/platform-compatibility.md) only when preflight reports `ACTION_REQUIRED`/`BLOCKED` or platform setup is requested.
3. Run `python scripts/validate_intake.py <intake.json>` and `python scripts/plan_sources.py <intake.json> --output <source-plan.json>`.
4. For `actual` collection, read [references/collection-and-evidence.md](references/collection-and-evidence.md). Use only registered official endpoints. Read the browser section only when current listings are requested.
5. Before analysis, read [references/analysis-and-matching.md](references/analysis-and-matching.md). If `task_mode` is `MARKET_REPORT_WITH_MATCHING`, candidates are required.
6. Before writing, read [references/report-writing-and-design.md](references/report-writing-and-design.md) and select the communication mode. For broker-to-customer delivery, read [references/customer-sales-copy.md](references/customer-sales-copy.md). Read [references/extended-buyer-decision-report.md](references/extended-buyer-decision-report.md) and [references/customer-sales-golden-v3.md](references/customer-sales-golden-v3.md) for the canonical page hierarchy and visual baseline.
7. Run only `scripts/run_report.ps1`, which must prepare, audit, build, render, and validate through `EZIWORK_GOLDEN_V3` version `3.1.0`. Do not create a report-specific builder or call a legacy compact renderer. Inspect every rendered page before delivery.

Read [references/extension-guide.md](references/extension-guide.md) only when adding a new source, property route, metric, matching rule, or report section.

## Non-negotiable boundaries

- Never invent a price, count, trend, source, listing, condition, or permission status.
- Never combine completed transactions and asking prices into one synthetic market price.
- Preserve cancelled transactions in raw evidence and exclude them from market aggregates.
- Treat the current reporting month as provisional.
- Monthly rent keeps deposit and rent separate unless the user supplies a dated conversion rule and source.
- A browser sample is a checked sample, not a complete inventory. Stop on CAPTCHA, blocking, re-authentication, uncertain identity, or repeated failure.
- `demo` values must display `교육용 예시 · 실제 시세가 아님` on every page.
- `HOLD` blocks customer HTML/PDF generation. Do not bypass the audit.
- A standard report is releasable only when HTML metadata shows `report-engine=EZIWORK_GOLDEN_V3`, `report-engine-version=3.1.0`, `report-profile=EXTENDED_9`, and exactly nine pages.
- The report is a consultation aid, not an appraisal, legal/tax opinion, permit, loan/guarantee decision, or price promise.

## Completion

Return the HTML, PDF, and evidence-audit links first. Then state the target, basis date, evidence mode, release result, collected scope, missing sources, and remaining field checks.
