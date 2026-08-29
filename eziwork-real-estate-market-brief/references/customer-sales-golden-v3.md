# Customer-sales golden V3

Use this baseline for every standard report. `CUSTOMER_SALES` and `BUYER_ADVISORY` may use different decision language, but both must use `report_profile=EXTENDED_9`, `report-engine=EZIWORK_GOLDEN_V3`, and the same approved visual system. Its purpose is to preserve the approved quality level across targets while keeping every factual claim target-specific.

## Conversion and message contract

The reader journey is `관심 → 신뢰 → 현장 방문 → 조건 상담`. Each page needs one verified reason to continue reading or one value driver to verify on site. Do not expose internal offer prices, ceilings, walk-away rules, or a dominant negative verdict. Keep confirmed material defects, rights issues, safety problems, arrears, and contract restrictions explicit.

The final customer action is normally `현장 방문 → 세대 가치 확인 → 고객에게 적합한 계약 조건 상담`. Price evidence supports comparison; it does not order the customer to discount or abandon the property.

## Approved visual signature

- A4 portrait, exactly nine purposeful pages, 15 mm side padding, stable footer space, and visible `NN / 09` numbering.
- EZIWORK dark blue `#082f58`, bright blue `#0a67ff`, pale blue surfaces, and one warm orange accent. Use green or blue for value-confirmation cards; do not use red merely because a condition is unresolved.
- Large Korean question typography, rounded white cards, one dominant chart or route visual per evidence page, generous whitespace, and a subtle property-name watermark.
- Reuse `../assets/customer-sales-extended-v3.css` as the starting stylesheet. Adapt content dimensions without shrinking text below readable print size.
- Cover: use a verified, unbranded property image only when identity and usage are appropriate. Otherwise use the approved dark-blue-to-white EZIWORK gradient. Never crop, blur, or cover another brokerage or platform mark.
- Prologue: the customer question is the only large title. Do not add an editorial headline above it.
- Walking routes: show the address and only verified destinations within 10 walking minutes. Include route, minutes, distance, provider, and basis date; omit out-of-range categories without placeholders.
- Price and transaction charts: keep completed deals, asking prices, and external price bands visually distinct. Move labels when they collide; do not accept overlapping annotations.
- Final page: retain the property fit, local price/volume direction, dated rate context, value drivers to inspect, and a single consultation CTA. Macro warnings must not dominate.

## Nine-page sales hierarchy

1. Cover: target, building/area, budget and horizon in a confident, uncluttered visual.
2. Prologue: direct customer question, analysis scope, and on-site consultation band.
3. Target/value frame: known facts, budget context, holding intent, and three on-site value drivers.
4. Location/routes: verified routes within the display threshold only.
5. Price position: subject budget, checked asks, price band, and value-confirmation copy.
6. Completed transactions: official deals and why unit condition can explain dispersion.
7. Market activity: volume and price direction framed as marketability and choice-set context.
8. Competitiveness: same-building, comparable-deal, and current-listing comparison without internal anchors.
9. Conclusion: fit, market context, visit checklist, and consultation action.

## Release gates

Reject the draft when any of the following is true:

- an extended buyer decision was rendered through the compact six-page builder;
- HTML metadata does not show `EZIWORK_GOLDEN_V3` version `3.1.0` or the page count is not exactly nine;
- a customer-sales page exposes an initial offer, ceiling, walk-away price, or `계약 보류` conclusion;
- a third-party-branded property photo is present;
- a walking-route card exceeds the chosen 10-minute threshold without an explicit user request;
- the report has blank pages, missing sources, overlapping chart labels, footer collisions, unreadable notes, or fewer/more than nine pages;
- the last page has no visit or consultation action.

Render every page to PNG and inspect the full set before release. Structural validation does not replace visual inspection.
