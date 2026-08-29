# Analysis and listing matching

## Comparable selection

- `APT`, `ROWHOUSE`, `OFFICETEL`: same target name and selected exclusive-area interval.
- `DETACHED_HOUSE`, `LAND`, `COMMERCIAL`: selected legal dong/lot hint and explicit land/building-area interval.
- Never expand the area, building, lot, or district automatically. Record a user-approved relaxation in the report.
- Preserve zero-result periods instead of quietly widening the scope.

Exclude cancelled rows from every price metric while retaining them in raw evidence. The current calendar month is provisional and does not establish a completed-period trend.

## Metrics

For `SALE`, calculate valid count, latest valid price, minimum, median, maximum, and complete-month trend when at least two comparable periods exist.

For `JEONSE`, use the deposit as the price axis and keep renewed/new contracts distinguishable when the source provides the fields.

For `MONTHLY_RENT`, show deposit and monthly rent separately and use a scatter or table. Do not calculate a jeonse-equivalent value unless the intake contains a dated rate, source, and explicit request.

For land or commercial sale, show total price and price per square metre separately only when the area denominator is present and comparable.

Do not emit `NaN`, `Infinity`, or a trend based on fewer than two observations. Use `자료 부족`, `확인 불가`, or `산정 불가`.

## Matching contract

Criteria use dotted paths into a candidate object:

```json
{
  "must_haves": [
    {"field": "price_krw", "operator": "lte", "value": 2500000000, "label": "예산 이내"}
  ],
  "preferences": [
    {"field": "direction", "operator": "eq", "value": "남향", "label": "남향"},
    {"field": "attributes.move_in_ready", "operator": "eq", "value": true, "label": "즉시 입주"}
  ]
}
```

Supported operators are `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `in`, `contains`, and `between`.

1. Deduplicate on `listing_id`; when it is absent, use the normalized tuple of name, price/deposit/rent, area, and floor.
2. Exclude a candidate only when a must-have is verifiably false. A missing must-have value becomes `확인 필요` and stays below verified candidates.
3. Score every preference equally: `matched preferences / all preferences * 100`.
4. Missing preference data is not a match and lowers the score.
5. Sort verified must-have passes first, then unresolved candidates, then score descending, then original order. Do not call the first row a guaranteed best property.

The report shows the score, matched conditions, missing conditions, failed conditions, and source timestamp. It does not hide candidates solely because their score is low.
