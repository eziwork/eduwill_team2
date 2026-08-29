# Terra High 100 visual quality contract

Use this contract for every standard output from this skill. It was calibrated against the user-approved nine-page EZIWORK buyer-decision reference without copying customer-specific facts into the reusable skill.

## Reference-derived page rhythm

1. Cover: navy field, very large Korean title, customer question, 3–4 rounded fact pills, controlled navy-to-light transition, brand and `01 / 09`.
2. Prologue: customer question, six scope cards, one decisive dark band.
3. Subject frame: three KPI cards, comparison table, interpretation card, three-step value or negotiation ladder.
4. Location: target address and one or two large verified walking-route images. Never show an unverified facility.
5. Price position: three KPI cards, one dominant price visual, two interpretation cards, visible source note.
6. Official transactions: dominant evidence table/visual, interpretation, and a strong conclusion band.
7. Market activity: KPI row, bar/line evidence visual when data permits, four compact interpretation cards.
8. Current competition: KPI row, listing distribution visual, two comparison cards, action band, source note.
9. Final decision: navy field, clear conclusion, evidence/condition table, next actions, exception or limitation condition, orange action block, detailed sources.

## Communication-mode separation

`CUSTOMER_SALES` uses value discovery, on-site confirmation, and consultation language. It must not contain buyer-only offer anchors, a negotiation ceiling, “추격 금지”, “계약금 송금 금지”, or “즉시 계약 보류”.

`BUYER_ADVISORY` may show a first offer, conditional ceiling, break-even condition, hold condition, and risk language only when each numeric value is user supplied or backed by a dated calculation record. Missing numbers remain visibly unresolved; do not infer a number merely to fill the design.

## Automated 100-point gate

The score is all-or-nothing by category and totals 100:

- Structure 25: file readable, nine A4 pages, nonblank pages, numbered sequence.
- Metadata 20: Golden V3 engine/version/profile plus Terra High profile/model/reasoning metadata.
- Layout 20: nine DOM sheets, no viewport overflow, no element outside its sheet, no broken images, no unexpected print-page count.
- Visual system 20: navy cover/final, light interior pages, required palette anchors, sufficient nonwhite content density.
- Content safety 15: communication-mode leakage checks, target/source/verification presence, demo labeling rules.

Any hard-gate failure makes the deliverable non-releasable even if the arithmetic subtotal is high. Release only at `100/100`.

## Reference comparison

When `--reference-pdf` is supplied, rasterize candidate and reference at the same dimensions. Report:

- `pixel_exact_pages`: count of pages whose rendered PNG hashes match exactly.
- `pixel_exact_percent`: exact equal pixels over all comparable pixels.
- `perceptual_similarity_percent`: normalized RGB mean-absolute similarity.

Pixel equality is expected only when reproducing the same frozen HTML/assets/runtime. For a different property or evidence set, enforce the structural and visual contract and use the reference result as calibration, not as a requirement to copy its content geometry blindly.
