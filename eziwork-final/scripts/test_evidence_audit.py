from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_audit import RELEASE_CONDITIONAL, RELEASE_HOLD, RELEASE_PASS, audit_request
from build_report import render_report, validate_request


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.artifact = self.base_dir / "normalized-inputs.json"
        self.artifact.write_text(json.dumps({"median": {"values": [4, 5, 6]}}), encoding="utf-8")
        self.artifact_hash = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.data = self._base_request()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _base_request(self) -> dict:
        source = {
            "id": "SRC-1",
            "grade": "A",
            "lane": "closed_or_reported_transactions",
            "name": "공식 거래 원자료",
            "url": "https://example.test/source",
            "as_of": "2026-08-27",
            "retrieved_at": "2026-08-27T10:00:00+09:00",
            "query_conditions": {"target": "테스트 단지", "period": "2026-01~2026-03"},
            "scope": "테스트 거래 3건",
            "limitation": "단위 테스트용",
        }
        group = {
            "id": "GRP-1",
            "lane": "closed_or_reported_transactions",
            "required_for_question": True,
            "status": "COMPLETE",
            "source_ids": ["SRC-1"],
            "coverage": {
                "expected_periods": ["2026-01", "2026-02", "2026-03"],
                "completed_periods": ["2026-01", "2026-02", "2026-03"],
                "source_total_count": 3,
                "fetched_rows": 3,
            },
            "counts": {"raw_rows": 3, "normalized_rows": 3, "excluded_rows": 0, "parse_failed_rows": 0, "used_rows": 3},
            "exclusions": [],
            "errors": [],
            "artifacts": [{"path": self.artifact.name, "sha256": self.artifact_hash}],
            "completeness_basis": "계획한 3개 기간과 원문 건수를 모두 대조함",
        }
        calculations = [{
            "id": "CALC-MEDIAN",
            "operation": "median",
            "inputs": {"values": [4, 5, 6]},
            "input_artifact_path": self.artifact.name,
            "input_key": "median",
            "output": 5,
            "display_value": "5억",
            "tolerance": 0.000001,
            "unit": "억원",
            "rounding": "소수 둘째 자리",
        }]
        claims = [
            {
                "id": "CLAIM-TARGET",
                "kind": "direct",
                "statement": "분석 대상은 테스트 단지 전용 84㎡ 매매입니다.",
                "source_ids": ["SRC-1"],
                "evidence_group_ids": ["GRP-1"],
                "scope": "complete",
                "limitation": "단위 테스트 대상",
            },
            {
                "id": "CLAIM-MEDIAN",
                "kind": "calculated",
                "statement": "완전 수집 자료의 중앙값은 5억원입니다.",
                "display_value": "5억",
                "source_ids": ["SRC-1"],
                "evidence_group_ids": ["GRP-1"],
                "calculation_id": "CALC-MEDIAN",
                "scope": "complete",
                "limitation": "테스트 범위에 한함",
            },
            {
                "id": "CLAIM-VISUAL",
                "kind": "direct",
                "statement": "완전 수집 자료의 그래프 값은 4, 5, 6억원입니다.",
                "source_ids": ["SRC-1"],
                "evidence_group_ids": ["GRP-1"],
                "scope": "complete",
                "limitation": "테스트 범위에 한함",
            },
            {
                "id": "CLAIM-ACTION",
                "kind": "interpretive",
                "statement": "가격 외 매물조건도 추가 확인해야 합니다.",
                "source_ids": ["SRC-1"],
                "evidence_group_ids": ["GRP-1"],
                "scope": "complete",
                "limitation": "현장조건 미포함",
            },
        ]
        return {
            "mode": "sale",
            "evidence_mode": "actual",
            "basis_date": "2026-08-27",
            "target": {
                "name": "테스트 단지",
                "address": "서울특별시 테스트구",
                "descriptor": "전용 84㎡ · 매매",
                "image_path": "",
                "map_image_path": "",
                "map_link": "",
                "map_source_id": "",
                "claim_ids": ["CLAIM-TARGET"],
            },
            "customer": {
                "role": "매수인",
                "question": "5억에 사도 괜찮을까요?",
                "scope": "가격과 조건을 함께 확인합니다.",
                "claim_ids": ["CLAIM-MEDIAN", "CLAIM-ACTION"],
            },
            "brand": {"name": "EZIWORK", "color": "#2c61ef", "agent_name": "", "contact": ""},
            "sources": [source],
            "evidence_groups": [group],
            "calculations": calculations,
            "claims": claims,
            "metrics": [
                {"label": "중앙값", "value": "5억", "note": "완전 수집", "claim_id": "CLAIM-MEDIAN"},
                {"label": "비교값", "value": "5억", "note": "완전 수집", "claim_id": "CLAIM-MEDIAN"},
                {"label": "검토값", "value": "5억", "note": "완전 수집", "claim_id": "CLAIM-MEDIAN"},
            ],
            "overview": {
                "title": "가격을 어떻게 볼까요?",
                "paragraphs": ["중앙값은 5억원입니다."],
                "takeaway": "가격 외 조건을 함께 확인합니다.",
                "claim_ids": ["CLAIM-MEDIAN", "CLAIM-ACTION"],
                "source_ids": ["SRC-1"],
            },
            "sections": [{
                "title": "5억원은 어느 위치일까요?",
                "lead": "완전 수집 자료를 비교했습니다.",
                "caption": "단위 억원",
                "body": "가격 외 조건도 확인합니다.",
                "takeaway": "추가 확인이 필요합니다.",
                "claim_ids": ["CLAIM-MEDIAN", "CLAIM-ACTION"],
                "source_ids": ["SRC-1"],
                "visual": {
                    "type": "line",
                    "min": 4,
                    "max": 6,
                    "labels": ["A", "B", "C"],
                    "series": [{"name": "거래", "values": [4, 5, 6]}],
                    "claim_ids": ["CLAIM-VISUAL"],
                },
            }],
            "checklist": [
                {"title": "원자료", "body": "최신 상태 확인", "claim_id": "CLAIM-ACTION"},
                {"title": "매물조건", "body": "현장조건 확인", "claim_id": "CLAIM-ACTION"},
                {"title": "다음 행동", "body": "계약 전 재조회", "claim_id": "CLAIM-ACTION"},
            ],
            "summary": {
                "paragraphs": ["중앙값은 5억원이며 추가 확인이 필요합니다."],
                "claim_ids": ["CLAIM-MEDIAN", "CLAIM-ACTION"],
                "cards": [
                    {"body": "가격 외 조건 확인", "claim_id": "CLAIM-ACTION"},
                    {"body": "원자료 재조회", "claim_id": "CLAIM-ACTION"},
                    {"body": "현장 확인", "claim_id": "CLAIM-ACTION"},
                ],
            },
            "disclaimer": "본 자료는 중개 상담 보조자료이며 감정평가나 법률 판단을 대신하지 않습니다.",
        }

    def test_complete_evidence_passes(self) -> None:
        result = audit_request(self.data, self.base_dir)
        self.assertEqual(RELEASE_PASS, result["derived_release_status"], result["errors"])

    def test_complete_actual_request_builds_with_fingerprint(self) -> None:
        data = copy.deepcopy(self.data)
        data["_base_dir"] = str(self.base_dir)
        errors = validate_request(data)
        self.assertEqual([], errors)
        rendered = render_report(data)
        self.assertIn('name="evidence-audit-sha256"', rendered)
        self.assertIn('name="derived-release-status" content="PASS"', rendered)

    def test_held_request_is_rejected_by_builder_validation(self) -> None:
        data = copy.deepcopy(self.data)
        data["_base_dir"] = str(self.base_dir)
        data["metrics"][0]["value"] = "99억"
        errors = validate_request(data)
        self.assertTrue(errors)
        self.assertEqual(RELEASE_HOLD, data["_evidence_audit"]["derived_release_status"])

    def test_hallucinated_metric_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["metrics"][0]["value"] = "99억"
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("99" in error or "differs" in error for error in result["errors"]))

    def test_calculation_mismatch_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["calculations"][0]["output"] = 8
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("output mismatch" in error for error in result["errors"]))

    def test_artifact_hash_mismatch_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["evidence_groups"][0]["artifacts"][0]["sha256"] = "0" * 64
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("sha256 mismatch" in error for error in result["errors"]))

    def test_missing_period_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["evidence_groups"][0]["coverage"]["completed_periods"].pop()
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("period coverage" in error for error in result["errors"]))

    def test_complete_without_coverage_proof_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["evidence_groups"][0]["coverage"] = {}
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("completeness proof" in error for error in result["errors"]))

    def test_formatted_calculation_value_mismatch_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["claims"][1]["display_value"] = "6억"
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("display_value differs" in error for error in result["errors"]))

    def test_sample_whole_market_claim_is_held(self) -> None:
        data = copy.deepcopy(self.data)
        data["evidence_groups"][0]["status"] = "SAMPLE_ONLY"
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_HOLD, result["derived_release_status"])
        self.assertTrue(any("scope is not sample" in error for error in result["errors"]))

    def test_explicitly_limited_sample_is_conditional(self) -> None:
        data = copy.deepcopy(self.data)
        data["evidence_groups"][0]["status"] = "SAMPLE_ONLY"
        for claim in data["claims"]:
            claim["scope"] = "sample"
            claim["statement"] = "확인한 표본 기준입니다. " + claim["statement"]
            claim["limitation"] = "확인한 표본 밖 전체 시장은 설명하지 않음"
        for metric in data["metrics"]:
            metric["note"] = "확인한 표본"
        data["target"]["name"] = "확인한 표본 대상"
        data["customer"]["scope"] += " 확인한 표본 기준입니다."
        data["overview"]["paragraphs"].append("확인한 표본 기준입니다.")
        data["sections"][0]["caption"] = "확인한 표본 · 단위 억원"
        data["sections"][0]["visual"]["sample_note"] = "확인한 표본"
        data["summary"]["paragraphs"].append("확인한 표본 기준입니다.")
        for card in data["summary"]["cards"]:
            card["body"] += " · 확인한 표본"
        for item in data["checklist"]:
            item["body"] += " · 확인한 표본"
        result = audit_request(data, self.base_dir)
        self.assertEqual(RELEASE_CONDITIONAL, result["derived_release_status"], result["errors"])


if __name__ == "__main__":
    unittest.main()
