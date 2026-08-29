# Extended nine-page buyer-decision report

Use this nine-page hierarchy for every standard real-estate brief. Apply the communication mode selected in [report-writing-and-design.md](report-writing-and-design.md). For broker-to-customer delivery, the nine pages should build informed interest and lead to an on-site visit; for explicitly requested independent advice, they may emphasize downside and negotiation. Preserve the evidence boundaries in the main skill. Missing evidence must remain visible; never fill a page with invented facts.

For a broker-facing `CUSTOMER_SALES` run, [customer-sales-golden-v3.md](customer-sales-golden-v3.md) is the approved design and message baseline. Reuse `../assets/customer-sales-extended-v3.css` instead of recreating a generic six-page appearance.

## Nine-page contract

1. **Cover** — Use a strong Korean title, the target property and building, and the basis date. Use a large target-property image in the lower portion only when it is verified and free of third-party branding; otherwise use a clean white-to-brand-color gradient. Keep the typeface consistent across the report.
2. **Prologue** — Use the customer's decision question itself as the only major title. Do not add an editorial headline above it that restates or competes with the question. Follow with one paragraph explaining what the report analyzes, then compact analysis-scope cards and one action-oriented decision band. In `CUSTOMER_SALES`, the band recommends the on-site check or consultation rather than a discounted offer.
3. **Target and decision frame** — Separate known facts, customer preferences, budget, holding period, resale intention, and unresolved unit conditions. In `CUSTOMER_SALES`, present unknown floor, repair, view, and management condition as value drivers to confirm; keep confirmed rights or safety problems explicit.
4. **Location and walking routes** — Show the address and target pin. By default, display only verified destinations reachable within 10 walking minutes, with the walking time, distance, and route from the property. Do not create cards or placeholders for categories outside the threshold. State the 10-minute display filter once and include the provider and basis date.
5. **Asking-price position** — Show the checked listing sample as asking prices, including visible low and high bounds, the subject price, building/area scope, and sample limitations. Never merge asking prices with completed transactions.
6. **Completed transactions** — Plot official completed transactions over time, identify the comparable scope, exclude cancelled rows from aggregates, and label any especially recent or same-building evidence.
7. **Market activity** — Show volume and median-direction evidence at the relevant complex or district/area tier. In `CUSTOMER_SALES`, explain what the activity means for future marketability and selection; in `BUYER_ADVISORY`, also explain liquidity risk. Never predict a guaranteed future price.
8. **Price competitiveness** — Compare the subject price with same-building evidence, comparable transactions, and checked current listings. In `CUSTOMER_SALES`, explain the current choice set and which unit conditions strengthen value. Put initial offer, ceiling, and walk-away scenarios only in `BUYER_ADVISORY` or an explicitly requested internal memo.
9. **Conclusion and market environment** — Summarize the property's fit, verified strengths, market context, value drivers to inspect, and next consultation action. Cite time-sensitive rate and market facts with dates, but do not let macro warnings dominate a customer-sales conclusion. Keep the property-name or brand watermark subtle in the background.

## Prologue copy rules

- Prefer a direct question title such as `앞으로 집값이 더 떨어질 것 같은데, 지금 2억원에 사도 괜찮을까요?` when that is the customer's actual question.
- Do not pair that question with a second large headline such as `질문은 단순하지만, 답은 시장에 달려 있습니다`. The duplicate hierarchy makes the real question look secondary.
- The explanation paragraph should say which evidence will be compared and why the conclusion is conditional. It should not announce an unsupported answer.
- The bottom decision band must read as a natural action sentence. In `CUSTOMER_SALES`, prefer `현장에서 세대 상태를 확인하고 고객에게 적합한 계약 조건을 상담해 보세요.`
- Avoid proposal prices, negotiation ceilings, and compressed fragments such as `1.80억 제안 / 1.90~1.95억 조건부 상단` in a customer-facing handout. They belong only in `BUYER_ADVISORY` or an explicitly requested internal memo.
- When a proposed price or ceiling is allowed in an internal mode, derive it from visible evidence and label it as a negotiation judgment, not an appraisal value.

## Visual and evidence rules

- Use A4 portrait, a restrained EZIWORK blue/dark-blue base, one warm accent for warnings or negotiation, large Korean question typography, rounded white cards, and generous whitespace.
- Use a property image on the cover only when its identity and use are appropriate for the report. Never publish a listing or property photo containing another brokerage, platform, photographer, or service name, logo, or watermark. Do not crop or blur branding to conceal it; remove the entire photo and use a clean white-based EZIWORK gradient instead. Provider attribution that is legally or operationally required on sourced route maps remains visible.
- Use a low-opacity property-name or EZIWORK watermark on inside pages. The watermark must never reduce chart or text readability.
- Give each evidence page one dominant visual. Charts must show units, time range, comparable scope, and the difference between actual transactions and current asks.
- Route maps must be static, print-safe, and sourced. Each route should originate at the subject property and make the destination category legible. Unless the user requests a broader comparison, show only verified routes of 10 walking minutes or less; omit out-of-range categories instead of presenting them as negative cards.
- When macro analysis is requested, include both interest-rate movement and the local market's price/volume direction. Distinguish sourced fact from interpretation and avoid certainty language.

## Build and QA

- `run_report.ps1` is the mandatory entrypoint. It prepares the normalized request and calls `build_report.py`, which delegates every standard report to `EZIWORK_GOLDEN_V3` version `3.1.0`.
- Never create a report-specific standalone builder. A different target or question must be expressed as normalized input and role-specific content inside the same engine.
- Render at the final A4 size and inspect all nine pages. Check the prologue title hierarchy, communication-mode consistency, decision-band wrapping, route-map labels, chart legends, low/high asking-price labels, watermark contrast, source links, page numbers, and final-action wording. A `CUSTOMER_SALES` report must not expose internal offer or ceiling prices.
- A nine-page report is complete only when all nine distinct page purposes are present. If evidence for a page is missing, keep the nine-page profile and use a designed limitation component that names the missing evidence and next check; never fall back to a compact profile or pad with generic prose.
