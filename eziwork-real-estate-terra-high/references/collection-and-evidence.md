# Collection and evidence

## Official route matrix

The registered MOLIT RTMS routes support:

- `APT`, `ROWHOUSE`, `DETACHED_HOUSE`, `OFFICETEL`: `SALE`, `JEONSE`, `MONTHLY_RENT`
- `LAND`, `COMMERCIAL`: `SALE`

Land or commercial rent has no bundled official unit-level route. Record `UNAVAILABLE`; accept traceable user-provided or licensed evidence without relabelling it as official.

BuildingHUB, VWorld, KOSIS, and Asil are extension candidates only. The registry documents them, but this release does not claim an automatic collector for them.

## Plan and collect

```powershell
python scripts/validate_intake.py path\to\intake.json
python scripts/plan_sources.py path\to\intake.json --output path\to\source-plan.json
```

For a planned RTMS route, run:

```powershell
pwsh -NoProfile -File scripts/collect_molit_rtms.ps1 `
  -ConfigPath path\to\intake.json `
  -OutputRoot path\to\report\official
```

Use `-DryRun` to verify the route and redacted query without a key. The collector saves immutable raw XML, normalized JSON/CSV, a collection manifest, and cancelled rows. Do not edit raw responses after collection.

Save a service key only through UTF-8 standard input:

```powershell
pwsh -NoProfile -File scripts/save_provider_api_key.ps1 -Provider DATA_GO_KR
```

On Windows this stores the key with current-user DPAPI. On macOS it stores the key in the current user's Keychain. A Windows `.dpapi` file is not portable to macOS. `DATA_GO_KR_SERVICE_KEY` may be used as a process environment fallback on either platform.

`DATA_GO_KR` is the fixed default credential reference for the bundled MOLIT RTMS routes. Register the service key once in the current operating system's secure store; do not place the plaintext key in `SKILL.md`, source code, JSON, commands, reports, or logs.

Never print or interpolate the key into a URL, report, screenshot, saved command, or log.

## Public listings and candidate input

Prefer a user-provided JSON or CSV. A browser-observed file may contain at most the visible research sample selected for the report. Stop on CAPTCHA, blocking, re-authentication, uncertain identity, or repeated timeout.

Canonical JSON:

```json
{
  "source": {
    "name": "네이버페이 부동산",
    "url": "https://new.land.naver.com/",
    "retrieved_at": "2026-08-29T10:00:00+09:00",
    "quality_status": "SAMPLE_ONLY",
    "query_conditions": "대상·거래유형·동·면적 필터"
  },
  "listings": [
    {
      "listing_id": "sample-001",
      "name": "101동 중층",
      "price_krw": 2400000000,
      "deposit_krw": null,
      "monthly_rent_krw": null,
      "exclusive_area_sqm": 84.9,
      "floor": 10,
      "direction": "남향",
      "verified_at": "2026-08-29",
      "attributes": {"school_zone": true, "move_in_ready": false}
    }
  ]
}
```

Preserve the visible ad count and deduplicated candidate count separately when available. A sample cannot support a whole-market inventory, ranking, minimum, maximum, or range claim unless the wording explicitly says `확인한 표본`.

## Evidence lanes

Keep four lanes separate:

- `closed_or_reported_transactions`
- `current_public_listings`
- `official_rules_and_status`
- `field_or_private_confirmations`

Every `actual` source record includes an ID, grade, lane, original URL or internal-record label, basis date, retrieval time, reproducible query conditions, scope, and limitation. Every artifact includes its path and SHA-256.

The preparation script creates the evidence groups, counts, exclusions, calculations, claims, and hashes. `COMPLETE` or `ZERO_RESULT` official groups may produce `PASS`; an explicitly limited listing sample produces `PASS WITH CONDITIONS`; missing required evidence, a changed artifact, calculation mismatch, or unresolved collection error produces `HOLD`.
