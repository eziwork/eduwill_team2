# Intake v1.0 and routing

Normalize natural language or a compact line into one user-facing JSON contract. The user never needs to author sources, hashes, calculations, claims, charts, or report copy.

## Compact input

```text
대상·지역 / 물건유형 / 거래유형 / 동·면적·필지 범위 / 고객입장 / 판단질문 / 1·3·5·7년 / actual 또는 demo
```

Example:

```text
잠실엘스·서울 송파구 / 아파트 / 매매 / 전체 동·전용 84㎡대 / 매수 / 23억원에 계약해도 될까요? / 3년 / actual
```

For listing matching, append:

```text
후보파일 / 필수조건 / 선호조건
```

## Canonical contract

```json
{
  "intake_version": "1.0",
  "report_id": "target-sale-20260829",
  "task_mode": "MARKET_REPORT",
  "evidence_mode": "actual",
  "basis_date": "2026-08-29",
  "target": {
    "name": "잠실엘스",
    "address": "서울특별시 송파구 잠실동",
    "property_type": "APT",
    "lawd_cd": "11710",
    "lot_number_hint": null
  },
  "transaction": {"trade_type": "SALE"},
  "scope": {
    "building_mode": "ALL",
    "building_names": [],
    "area_mode": "SELECTED",
    "area_basis": "EXCLUSIVE",
    "requested_area_min_sqm": 84.0,
    "requested_area_max_sqm": 85.0
  },
  "customer": {
    "role": "BUY",
    "decision_question": "23억원에 계약해도 될까요?"
  },
  "communication": {
    "mode": "CUSTOMER_SALES",
    "report_profile": "AUTO",
    "conversion_goal": "SITE_VISIT_CONSULTATION"
  },
  "terms": {
    "proposed_price_krw": 2300000000,
    "deposit_krw": null,
    "monthly_rent_krw": null,
    "intended_use": null
  },
  "period": {"history_years": 3},
  "decision_context": {
    "budget_krw": 2300000000,
    "intended_holding_years": 3,
    "resale_intent": "SELL_IF_PRICE_RISES"
  },
  "collection": {
    "include_current_market": true,
    "permission_mode": "RESEARCH_SAMPLE",
    "max_detail_pages": 10,
    "listings_path": null
  },
  "matching": {
    "candidates_path": null,
    "must_haves": [],
    "preferences": []
  },
  "output": {
    "formats": ["html", "pdf"],
    "brand_name": "EZIWORK",
    "brand_color": "#2c61ef",
    "agent_name": null,
    "contact": null
  }
}
```

## Enumerations

- `task_mode`: `MARKET_REPORT`, `MARKET_REPORT_WITH_MATCHING`
- `evidence_mode`: `actual`, `demo`
- `property_type`: `APT`, `ROWHOUSE`, `DETACHED_HOUSE`, `OFFICETEL`, `LAND`, `COMMERCIAL`
- `trade_type`: `SALE`, `JEONSE`, `MONTHLY_RENT`
- `customer.role`: `BUY`, `SELL`, `TENANT`, `LANDLORD`, `OWNER`, `OPERATOR`
- `communication.mode`: `CUSTOMER_SALES`, `BUYER_ADVISORY`
- `communication.report_profile`: `AUTO`, `COMPACT_6`, `EXTENDED_9`
- `communication.conversion_goal`: `SITE_VISIT_CONSULTATION`, `INFORMED_DECISION`
- `scope.building_mode`: `ALL`, `SELECTED`, `NOT_APPLICABLE`
- `scope.area_mode`: `ALL`, `SELECTED`, `NOT_APPLICABLE`
- `collection.permission_mode`: `RESEARCH_SAMPLE` only in this educational release

## Minimum gate

Always require a supported task mode, evidence mode, precise target, property type, trade type, customer role, one decision question, and one of `1`, `3`, `5`, or `7` history years.

For a broker handout, set `communication.mode` to `CUSTOMER_SALES`. All standard report profile values, including legacy `COMPACT_6`, normalize to `EXTENDED_9` and the canonical `EZIWORK_GOLDEN_V3` renderer. The profile field remains input-compatible only; it must not select a different design engine. `period.history_years` controls evidence collection and is distinct from `decision_context.intended_holding_years`.

- `actual` official collection also needs a five-digit `lawd_cd` and a source route.
- `APT`, `ROWHOUSE`, and `OFFICETEL` normally need an exclusive-area scope.
- `DETACHED_HOUSE`, `LAND`, and `COMMERCIAL` need a lot/address hint and an explicit area or comparison scope when district-wide evidence is too broad.
- A price/deposit/rent is required only when the decision question asks whether a proposed condition is acceptable.
- `MARKET_REPORT_WITH_MATCHING` requires a candidate JSON/CSV and at least one must-have or preference.

Do not infer a unit number, parcel number, price, permission, intended use, or contract term. Do not silently broaden a building, area, or district range.

## Ask only material questions

Ask at most three short questions at a time and skip known facts. Questions are material when they select a different official dataset, change comparable rows, change the customer route, or determine whether the report can be `actual`.

Offer one year as the quick collection option and three years as the broader apartment comparison; never choose for the user.
