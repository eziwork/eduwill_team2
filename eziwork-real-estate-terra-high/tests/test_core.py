from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evidence_audit import audit_request  # noqa: E402
from build_report import render_report  # noqa: E402
from match_listings import match_candidates  # noqa: E402
from plan_sources import _load_registry, _transaction_route  # noqa: E402
from prepare_report import metric_summary, prepare  # noqa: E402
from validate_intake import validate_intake  # noqa: E402


class RouteTests(unittest.TestCase):
    def test_registry_exposes_ten_rtms_datasets_and_fourteen_combinations(self) -> None:
        registry = _load_registry(SCRIPTS)
        rtms = {key: value for key, value in registry["sources"].items() if value.get("provider") == "MOLIT_RTMS"}
        self.assertEqual(len(rtms), 10)
        combinations = {(item["property_type"], item["trade_type"]) for source in rtms.values() for item in source.get("supports", [])}
        self.assertEqual(len(combinations), 14)
        for property_type in ("APT", "ROWHOUSE", "DETACHED_HOUSE", "OFFICETEL"):
            for trade_type in ("SALE", "JEONSE", "MONTHLY_RENT"):
                self.assertIsNotNone(_transaction_route(registry, property_type, trade_type))
        self.assertIsNotNone(_transaction_route(registry, "LAND", "SALE"))
        self.assertIsNotNone(_transaction_route(registry, "COMMERCIAL", "SALE"))
        self.assertIsNone(_transaction_route(registry, "LAND", "JEONSE"))
        self.assertIsNone(_transaction_route(registry, "COMMERCIAL", "MONTHLY_RENT"))


class MetricTests(unittest.TestCase):
    def test_cancelled_and_missing_values_are_excluded(self) -> None:
        rows = [
            {"trade_type": "SALE", "contract_date": "2026-08-01", "deal_amount_krw": 500, "cancelled": False},
            {"trade_type": "SALE", "contract_date": "2026-07-01", "deal_amount_krw": 700, "cancelled": True},
            {"trade_type": "SALE", "contract_date": "2026-06-01", "deal_amount_krw": None, "cancelled": False},
        ]
        summary = metric_summary(rows, "SALE", "2026-08-29")
        self.assertEqual(summary["valid_count"], 1)
        self.assertEqual(summary["excluded"]["cancelled"], 1)
        self.assertEqual(summary["excluded"]["missing_metric"], 1)
        self.assertEqual(summary["median"], 500)
        self.assertEqual(summary["provisional_current_month_count"], 1)

    def test_monthly_rent_keeps_deposit_and_rent_as_pairs(self) -> None:
        rows = [{"trade_type": "MONTHLY_RENT", "contract_date": "2026-07-01", "deposit_krw": 50_000_000, "monthly_rent_krw": 1_200_000, "cancelled": False}]
        summary = metric_summary(rows, "MONTHLY_RENT", "2026-08-29")
        self.assertEqual(summary["pairs"], [{"deposit_krw": 50_000_000.0, "monthly_rent_krw": 1_200_000.0}])
        self.assertNotIn("jeonse_equivalent", summary)


class MatchingTests(unittest.TestCase):
    def test_hard_filter_equal_weight_missing_and_dedup(self) -> None:
        rows = [
            {"listing_id": "A", "name": "A", "price_krw": 500, "direction": "남향", "attributes": {"ready": True}},
            {"listing_id": "A", "name": "A duplicate", "price_krw": 500, "direction": "남향", "attributes": {"ready": True}},
            {"listing_id": "B", "name": "B", "price_krw": 450, "direction": "동향", "attributes": {}},
            {"listing_id": "C", "name": "C", "price_krw": 650, "direction": "남향", "attributes": {"ready": True}},
        ]
        result = match_candidates(
            rows,
            [{"field": "price_krw", "operator": "lte", "value": 600, "label": "예산"}],
            [
                {"field": "direction", "operator": "eq", "value": "남향", "label": "남향"},
                {"field": "attributes.ready", "operator": "eq", "value": True, "label": "입주"},
            ],
        )
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["excluded_count"], 1)
        self.assertEqual(result["results"][0]["candidate"]["listing_id"], "A")
        self.assertEqual(result["results"][0]["score"], 100.0)
        self.assertEqual(result["results"][1]["score"], 0.0)
        self.assertIn("입주", result["results"][1]["unknown_conditions"])


class IntakeTests(unittest.TestCase):
    def test_actual_customer_report_requires_office_name_and_logo(self) -> None:
        fixtures = SKILL_ROOT / "tests" / "fixtures"
        intake = json.loads((fixtures / "actual-intake.json").read_text(encoding="utf-8"))
        intake["output"].pop("brand_name")
        intake["output"].pop("logo_path")
        errors, _warnings = validate_intake(intake, fixtures)
        self.assertIn("output.brand_name is required for an actual customer report", errors)
        self.assertIn("output.logo_path is required for an actual customer report", errors)

    def test_unsupported_land_rent_is_warning_not_silent_substitution(self) -> None:
        intake = json.loads((SKILL_ROOT / "assets" / "demo-land-matching.json").read_text(encoding="utf-8"))
        intake["task_mode"] = "MARKET_REPORT"
        intake["matching"] = {"candidates_path": None, "must_haves": [], "preferences": []}
        intake["transaction"]["trade_type"] = "JEONSE"
        errors, warnings = validate_intake(intake, SKILL_ROOT / "assets")
        self.assertFalse(errors)
        self.assertTrue(any("no bundled official" in warning for warning in warnings))


class EndToEndPreparationTests(unittest.TestCase):
    def test_demo_request_audits_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = SKILL_ROOT / "assets" / "demo-apartment.json"
            request_path, _audit_path, release = prepare(Namespace(intake=intake, report_root=root, official_rows=None, official_manifest=None, listings=None))
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(release, "PASS")
            self.assertEqual(len(request["sections"]), 2)
            self.assertEqual(audit_request(request, root)["derived_release_status"], "PASS")

    def test_actual_fixture_is_pass_with_conditions(self) -> None:
        fixtures = SKILL_ROOT / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, _audit_path, release = prepare(
                Namespace(
                    intake=fixtures / "actual-intake.json",
                    report_root=root,
                    official_rows=fixtures / "actual-official-rows.json",
                    official_manifest=fixtures / "actual-manifest.json",
                    listings=fixtures / "actual-listings.json",
                )
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            audit = audit_request(request, root)
            self.assertEqual(release, "PASS WITH CONDITIONS", audit["errors"])
            self.assertEqual(audit["derived_release_status"], "PASS WITH CONDITIONS", audit["errors"])
            self.assertEqual(request["brand"]["name"], "검증 공인중개사사무소")
            self.assertEqual(request["brand"]["logo_path"], "assets/brand-logo.svg")
            self.assertTrue((root / "assets" / "brand-logo.svg").is_file())
            self.assertTrue(any(item["kind"] == "brand_logo" for item in audit["asset_manifest"]))

            request["_base_dir"] = str(root)
            html = render_report(request)
            self.assertIn('class="brand-logo"', html)
            self.assertIn("data:image/svg+xml;base64,", html)

    def test_customer_sales_auto_routes_budget_and_horizon_to_extended_nine(self) -> None:
        fixtures = SKILL_ROOT / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = json.loads((fixtures / "actual-intake.json").read_text(encoding="utf-8"))
            intake["output"]["logo_path"] = str((SKILL_ROOT / "assets" / "demo-broker-logo.svg").resolve())
            intake["communication"] = {
                "mode": "CUSTOMER_SALES",
                "report_profile": "AUTO",
                "conversion_goal": "SITE_VISIT_CONSULTATION",
            }
            intake["decision_context"] = {
                "budget_krw": 200_000_000,
                "intended_holding_years": 3,
                "resale_intent": "SELL_IF_PRICE_RISES",
            }
            intake_path = root / "intake-source.json"
            intake_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
            request_path, _audit_path, _release = prepare(
                Namespace(
                    intake=intake_path,
                    report_root=root / "report",
                    official_rows=fixtures / "actual-official-rows.json",
                    official_manifest=fixtures / "actual-manifest.json",
                    listings=fixtures / "actual-listings.json",
                )
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["communication_mode"], "CUSTOMER_SALES")
            self.assertEqual(request["report_profile"], "EXTENDED_9")
            self.assertEqual(request["conversion_goal"], "SITE_VISIT_CONSULTATION")
            request["_base_dir"] = str(root / "report")
            html = render_report(request)
            self.assertIn('<meta name="report-engine" content="EZIWORK_GOLDEN_V3">', html)
            self.assertIn('<meta name="report-engine-version" content="3.1.0">', html)
            self.assertIn('<meta name="report-quality-profile" content="TERRA_HIGH_100">', html)
            self.assertIn('<meta name="recommended-model" content="gpt-5.6-terra">', html)
            self.assertIn('<meta name="recommended-reasoning" content="high">', html)
            self.assertEqual(html.count('class="sheet page'), 9)

    def test_buyer_advisory_is_separate_and_does_not_invent_offer_numbers(self) -> None:
        fixtures = SKILL_ROOT / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = json.loads((fixtures / "actual-intake.json").read_text(encoding="utf-8"))
            intake["output"]["logo_path"] = str((SKILL_ROOT / "assets" / "demo-broker-logo.svg").resolve())
            intake["communication"] = {
                "mode": "BUYER_ADVISORY",
                "report_profile": "EXTENDED_9",
                "conversion_goal": "INFORMED_DECISION",
            }
            intake["decision_context"] = {
                "budget_krw": 200_000_000,
                "intended_holding_years": 3,
                "resale_intent": "SELL_IF_PRICE_RISES",
            }
            intake_path = root / "buyer-intake.json"
            intake_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
            request_path, _audit_path, _release = prepare(
                Namespace(
                    intake=intake_path,
                    report_root=root / "report",
                    official_rows=fixtures / "actual-official-rows.json",
                    official_manifest=fixtures / "actual-manifest.json",
                    listings=fixtures / "actual-listings.json",
                )
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["_base_dir"] = str(root / "report")
            html = render_report(request)
            self.assertIn('content="BUYER_ADVISORY"', html)
            self.assertIn("매수 판단 리포트", html)
            self.assertIn("협상 가격 사다리", html)
            self.assertIn("추가 산정 필요", html)
            self.assertNotIn("고객에게 보여줄 가치", html)

    def test_buyer_advisory_uses_only_provenanced_numeric_recommendations(self) -> None:
        fixtures = SKILL_ROOT / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = json.loads((fixtures / "actual-intake.json").read_text(encoding="utf-8"))
            intake["output"]["logo_path"] = str((SKILL_ROOT / "assets" / "demo-broker-logo.svg").resolve())
            intake["communication"] = {"mode": "BUYER_ADVISORY", "report_profile": "EXTENDED_9", "conversion_goal": "INFORMED_DECISION"}
            intake["decision_context"] = {
                "budget_krw": 200_000_000,
                "intended_holding_years": 3,
                "first_offer_krw": 180_000_000,
                "conditional_ceiling_krw": 195_000_000,
                "hold_above_krw": 200_000_000,
                "break_even_price_krw": 205_000_000,
                "recommendation_basis": "사용자 제공 협상 시나리오와 공식 거래 비교",
                "recommendation_basis_date": "2026-08-29",
                "recommendation_source_ids": ["SRC-OFFICIAL", "SRC-LISTING"],
            }
            intake_path = root / "buyer-provenanced-intake.json"
            intake_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
            errors, _warnings = validate_intake(intake, root)
            self.assertFalse(errors, errors)
            request_path, _audit_path, _release = prepare(
                Namespace(
                    intake=intake_path,
                    report_root=root / "report",
                    official_rows=fixtures / "actual-official-rows.json",
                    official_manifest=fixtures / "actual-manifest.json",
                    listings=fixtures / "actual-listings.json",
                )
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["_base_dir"] = str(root / "report")
            html = render_report(request)
            self.assertIn("1.8억원 제안", html)
            self.assertIn("1.95억원 이내 조건부 결정", html)
            self.assertIn("검증된 손익분기 가격 · 2.05억원", html)

    def test_legacy_compact_seller_request_normalizes_to_same_golden_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake = json.loads((SKILL_ROOT / "assets" / "demo-apartment.json").read_text(encoding="utf-8"))
            intake["output"]["logo_path"] = str((SKILL_ROOT / "assets" / "demo-broker-logo.svg").resolve())
            intake["customer"]["role"] = "SELL"
            intake["customer"]["decision_question"] = "지금 매도 상담을 시작해도 괜찮을까요?"
            intake["communication"] = {
                "mode": "CUSTOMER_SALES",
                "report_profile": "COMPACT_6",
                "conversion_goal": "SITE_VISIT_CONSULTATION",
            }
            intake_path = root / "seller-intake.json"
            intake_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
            request_path, _audit_path, _release = prepare(
                Namespace(intake=intake_path, report_root=root / "report", official_rows=None, official_manifest=None, listings=None)
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["report_profile"], "EXTENDED_9")
            self.assertEqual(request["report_engine"]["id"], "EZIWORK_GOLDEN_V3")
            self.assertEqual(request["report_engine"]["legacy_profile_requested"], "COMPACT_6")
            request["_base_dir"] = str(root / "report")
            html = render_report(request)
            self.assertEqual(html.count('class="sheet page'), 9)
            self.assertIn("매도 조건 상담", html)


if __name__ == "__main__":
    unittest.main()
