from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pypdf import PdfReader


EXPECTED_PAGES = 9
A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89
PALETTE = {
    "navy": (8, 47, 88),
    "blue": (10, 103, 255),
    "orange": (243, 112, 33),
}


@dataclass
class Category:
    name: str
    maximum: int
    passed: bool
    checks: dict[str, bool]
    findings: list[str]

    @property
    def score(self) -> int:
        return self.maximum if self.passed else 0


def meta(html: str, name: str) -> str:
    match = re.search(rf'<meta\s+name=["\']{re.escape(name)}["\']\s+content=["\']([^"\']*)', html, re.I)
    return match.group(1) if match else ""


def rasterize(pdf: Path, output_dir: Path, pdftoppm: str) -> list[Path]:
    prefix = output_dir / "page"
    command = [pdftoppm, "-png", "-r", "150", str(pdf), str(prefix)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr.strip() or result.stdout.strip()}")
    return sorted(output_dir.glob("page-*.png"), key=lambda item: int(item.stem.split("-")[-1]))


def page_array(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def palette_fraction(array: np.ndarray, color: tuple[int, int, int], tolerance: int = 20) -> float:
    target = np.asarray(color, dtype=np.int16)
    distance = np.max(np.abs(array.astype(np.int16) - target), axis=2)
    return float(np.mean(distance <= tolerance))


def visual_checks(images: list[Path]) -> tuple[dict[str, bool], dict[str, Any], list[str]]:
    checks: dict[str, bool] = {}
    findings: list[str] = []
    metrics: dict[str, Any] = {"pages": [], "palette_fraction": {key: 0.0 for key in PALETTE}}
    arrays: list[np.ndarray] = []
    for index, image_path in enumerate(images, start=1):
        array = page_array(image_path)
        arrays.append(array)
        luminance = 0.2126 * array[:, :, 0] + 0.7152 * array[:, :, 1] + 0.0722 * array[:, :, 2]
        nonwhite = float(np.mean(np.any(array < 245, axis=2)))
        top = luminance[: max(1, array.shape[0] // 3), :]
        metrics["pages"].append(
            {
                "page": index,
                "width": int(array.shape[1]),
                "height": int(array.shape[0]),
                "mean_luminance": round(float(np.mean(luminance)), 3),
                "top_third_luminance": round(float(np.mean(top)), 3),
                "nonwhite_fraction": round(nonwhite, 6),
            }
        )
    if len(arrays) != EXPECTED_PAGES:
        return {"nine_rasters": False}, metrics, [f"expected {EXPECTED_PAGES} raster pages, found {len(arrays)}"]

    for name, color in PALETTE.items():
        fraction = sum(palette_fraction(array, color) for array in arrays) / len(arrays)
        metrics["palette_fraction"][name] = round(fraction, 8)
    checks["nine_rasters"] = True
    checks["navy_cover"] = metrics["pages"][0]["top_third_luminance"] < 125 and palette_fraction(arrays[0], PALETTE["navy"]) > 0.08
    checks["navy_final"] = metrics["pages"][8]["mean_luminance"] < 170 and palette_fraction(arrays[8], PALETTE["navy"]) > 0.18
    checks["light_interior"] = all(item["mean_luminance"] > 185 for item in metrics["pages"][1:8])
    checks["palette_anchors"] = all(metrics["palette_fraction"][name] > threshold for name, threshold in {"navy": 0.005, "blue": 0.00005, "orange": 0.00002}.items())
    checks["content_density"] = all(0.035 < item["nonwhite_fraction"] < 0.96 for item in metrics["pages"])
    for key, passed in checks.items():
        if not passed:
            findings.append(f"visual check failed: {key}")
    return checks, metrics, findings


def reference_comparison(candidate: list[Path], reference: list[Path]) -> dict[str, Any]:
    count = min(len(candidate), len(reference))
    exact_pages = 0
    equal_pixels = 0
    total_pixels = 0
    absolute_error = 0.0
    channel_values = 0
    page_results = []
    for index in range(count):
        candidate_hash = hashlib.sha256(candidate[index].read_bytes()).hexdigest()
        reference_hash = hashlib.sha256(reference[index].read_bytes()).hexdigest()
        hash_exact = candidate_hash == reference_hash
        a = page_array(candidate[index])
        b = page_array(reference[index])
        if a.shape != b.shape:
            with Image.fromarray(a) as image:
                a = np.asarray(image.resize((b.shape[1], b.shape[0]), Image.Resampling.LANCZOS), dtype=np.uint8)
            hash_exact = False
        equal = int(np.sum(np.all(a == b, axis=2)))
        pixels = int(a.shape[0] * a.shape[1])
        error = float(np.abs(a.astype(np.int16) - b.astype(np.int16)).sum())
        equal_pixels += equal
        total_pixels += pixels
        absolute_error += error
        channel_values += pixels * 3
        if hash_exact:
            exact_pages += 1
        page_results.append({"page": index + 1, "png_hash_exact": hash_exact, "equal_pixel_percent": round(equal / pixels * 100, 6)})
    return {
        "comparable_pages": count,
        "page_count_equal": len(candidate) == len(reference),
        "pixel_exact_pages": exact_pages,
        "pixel_exact_percent": round(equal_pixels / total_pixels * 100, 6) if total_pixels else 0.0,
        "perceptual_similarity_percent": round((1.0 - absolute_error / max(1, channel_values) / 255.0) * 100, 6),
        "pages": page_results,
    }


def make_category(name: str, maximum: int, checks: dict[str, bool], findings: list[str]) -> Category:
    return Category(name=name, maximum=maximum, passed=all(checks.values()) and not findings, checks=checks, findings=findings)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    html = args.html.read_text(encoding="utf-8")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    layout = json.loads(args.layout.read_text(encoding="utf-8"))
    reader = PdfReader(str(args.pdf))
    page_text = [page.extract_text() or "" for page in reader.pages]

    structure_checks = {
        "pdf_readable": True,
        "nine_pages": len(reader.pages) == EXPECTED_PAGES,
        "a4_pages": all(abs(float(page.mediabox.width) - A4_WIDTH_PT) <= 3 and abs(float(page.mediabox.height) - A4_HEIGHT_PT) <= 3 for page in reader.pages),
        "nonblank_pages": all(len(re.sub(r"\s+", "", text)) >= 10 for text in page_text),
        "numbered_sequence": all(f"{index:02d} / 09" in text or f"{index:02d}/09" in re.sub(r"\s+", "", text) for index, text in enumerate(page_text, start=1)),
    }
    structure_findings = [f"structure check failed: {key}" for key, passed in structure_checks.items() if not passed]

    metadata_checks = {
        "golden_engine": meta(html, "report-engine") == "EZIWORK_GOLDEN_V3" and meta(html, "report-engine-version") == "3.1.0",
        "extended_profile": meta(html, "report-profile") == "EXTENDED_9",
        "terra_quality_profile": meta(html, "report-quality-profile") == "TERRA_HIGH_100" and meta(html, "report-quality-profile-version") == "1.0.0",
        "terra_recommendation": meta(html, "recommended-model") == "gpt-5.6-terra" and meta(html, "recommended-reasoning") == "high",
        "communication_mode": meta(html, "communication-mode") in {"CUSTOMER_SALES", "BUYER_ADVISORY"},
    }
    metadata_findings = [f"metadata check failed: {key}" for key, passed in metadata_checks.items() if not passed]

    layout_checks = {
        "layout_status": layout.get("status") == "PASS",
        "nine_sheets": layout.get("sheet_count") == EXPECTED_PAGES,
        "no_broken_images": not layout.get("broken_images"),
        "no_overflow": not layout.get("overflows") and not layout.get("out_of_bounds"),
        "no_footer_collisions": not layout.get("footer_collisions"),
    }
    layout_findings = [f"layout check failed: {key}" for key, passed in layout_checks.items() if not passed]

    pdftoppm = args.pdftoppm or shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm was not found; pass --pdftoppm")
    with tempfile.TemporaryDirectory(prefix="eziwork-terra-candidate-") as temporary:
        candidate_images = rasterize(args.pdf, Path(temporary), pdftoppm)
        candidate_images_for_compare = list(candidate_images)
        visual_result, visual_metrics, visual_findings = visual_checks(candidate_images)
        comparison = None
        if args.reference_pdf:
            with tempfile.TemporaryDirectory(prefix="eziwork-terra-reference-") as reference_temporary:
                reference_images = rasterize(args.reference_pdf, Path(reference_temporary), pdftoppm)
                comparison = reference_comparison(candidate_images_for_compare, reference_images)

    communication_mode = meta(html, "communication-mode")
    combined_text = "\n".join(page_text)
    target_name = str(request.get("target", {}).get("name", ""))
    audit_fingerprint = meta(html, "combined-release-sha256")
    safety_checks = {
        "target_present": bool(target_name) and target_name in combined_text,
        "verification_present": bool(audit_fingerprint) and audit_fingerprint[:16] in re.sub(r"\s+", "", combined_text),
        "sources_present": 'class="sources"' in html and bool(request.get("sources")),
        "mode_separation": True,
        "demo_labeling": True,
    }
    if communication_mode == "CUSTOMER_SALES":
        safety_checks["mode_separation"] = not any(phrase in html for phrase in ("즉시 계약 보류", "추격 금지", "계약금 송금 금지", "조건부 상단", "1차 제안"))
    elif communication_mode == "BUYER_ADVISORY":
        safety_checks["mode_separation"] = "협상" in html and ("추가 산정 필요" in html or "recommendation_basis" in json.dumps(request, ensure_ascii=False))
    evidence_mode = str(request.get("evidence_mode", ""))
    demo_phrase = "교육용 예시 · 실제 시세가 아님"
    if evidence_mode == "demo":
        safety_checks["demo_labeling"] = all(demo_phrase in text for text in page_text)
    elif evidence_mode == "actual":
        safety_checks["demo_labeling"] = demo_phrase not in combined_text
    safety_findings = [f"content safety check failed: {key}" for key, passed in safety_checks.items() if not passed]

    categories = [
        make_category("structure", 25, structure_checks, structure_findings),
        make_category("metadata", 20, metadata_checks, metadata_findings),
        make_category("layout", 20, layout_checks, layout_findings),
        make_category("visual_system", 20, visual_result, visual_findings),
        make_category("content_safety", 15, safety_checks, safety_findings),
    ]
    score = sum(category.score for category in categories)
    hard_gate_pass = all(category.passed for category in categories)
    return {
        "quality_profile": "TERRA_HIGH_100",
        "quality_profile_version": "1.0.0",
        "score": score,
        "maximum": 100,
        "status": "PASS" if score == 100 and hard_gate_pass else "FAIL",
        "hard_gate_pass": hard_gate_pass,
        "runtime_model_verified": meta(html, "runtime-model-verified").lower() == "true",
        "recommended_model": meta(html, "recommended-model"),
        "recommended_reasoning": meta(html, "recommended-reasoning"),
        "categories": [asdict(category) | {"score": category.score} for category in categories],
        "visual_metrics": visual_metrics,
        "reference_comparison": comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score an EZIWORK Terra High PDF against the deterministic 100-point quality gate.")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-pdf", type=Path)
    parser.add_argument("--pdftoppm", default="")
    args = parser.parse_args()
    try:
        result = evaluate(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: visual quality gate failed: {exc}")
        return 3
    print(f"{result['status']}: Terra High visual quality {result['score']}/100 ({args.output.resolve()})")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
