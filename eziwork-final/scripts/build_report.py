from __future__ import annotations

import argparse
import base64
import html
import json
import math
import mimetypes
import re
from pathlib import Path
from typing import Any

from evidence_audit import RELEASE_HOLD, audit_request, write_audit


MODES = {
    "sale": ("매매", "매수인 · 매도인"),
    "jeonse": ("전세", "임차인 · 임대인"),
    "monthly_rent": ("월세", "임차인 · 임대인"),
    "commercial_lease": ("상가 임대", "점포 임차인 · 건물주"),
    "land_lease": ("토지 임대", "토지주 · 사업자"),
}

FORBIDDEN = (
    "고객에게는 이렇게 설명합니다",
    "고객에게 이렇게 정리해서 설명합니다",
    "중개사가 승인",
    "고객 전달 전",
    "영업용 멘트",
    "스킬 설계용",
)

STATUS_LABELS = {
    "확인": "ok",
    "추가 확인": "warn",
    "판단 보류": "hold",
    "적합": "ok",
    "주의": "warn",
    "보류": "hold",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def load_request(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_base_dir"] = str(path.resolve().parent)
    return data


def validate_request(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("mode") not in MODES:
        errors.append("mode must be one of: " + ", ".join(MODES))
    if data.get("evidence_mode") not in {"actual", "demo"}:
        errors.append("evidence_mode must be actual or demo")

    required = {
        "basis_date": data.get("basis_date"),
        "target.name": data.get("target", {}).get("name"),
        "target.descriptor": data.get("target", {}).get("descriptor"),
        "customer.role": data.get("customer", {}).get("role"),
        "customer.question": data.get("customer", {}).get("question"),
        "customer.scope": data.get("customer", {}).get("scope"),
        "brand.name": data.get("brand", {}).get("name"),
        "overview.title": data.get("overview", {}).get("title"),
        "overview.takeaway": data.get("overview", {}).get("takeaway"),
        "disclaimer": data.get("disclaimer"),
    }
    for key, value in required.items():
        if not isinstance(value, str) or not value.strip():
            errors.append(f"missing required string: {key}")

    if len(data.get("metrics", [])) != 3:
        errors.append("metrics must contain exactly 3 items")
    if not data.get("sections"):
        errors.append("sections must contain at least 1 analysis page")
    if len(data.get("checklist", [])) < 3:
        errors.append("checklist must contain at least 3 items")
    if len(data.get("summary", {}).get("cards", [])) != 3:
        errors.append("summary.cards must contain exactly 3 items")
    if not data.get("sources"):
        errors.append("sources must contain at least 1 record")

    serialized = json.dumps(data, ensure_ascii=False)
    for phrase in FORBIDDEN:
        if phrase in serialized:
            errors.append(f"forbidden internal phrase: {phrase}")

    source_ids = {str(item.get("id", "")) for item in data.get("sources", [])}
    if "" in source_ids:
        errors.append("every source needs an id")
    for index, section in enumerate(data.get("sections", []), start=1):
        for key in ("title", "lead", "caption", "body", "takeaway"):
            if not str(section.get(key, "")).strip():
                errors.append(f"sections[{index}] missing {key}")
        visual_type = section.get("visual", {}).get("type")
        if visual_type not in {"band", "bar", "line", "scatter", "matrix", "image"}:
            errors.append(f"sections[{index}] has unsupported visual type: {visual_type}")
        if data.get("evidence_mode") == "actual":
            ids = section.get("source_ids", [])
            if not ids:
                errors.append(f"sections[{index}] needs source_ids in actual mode")
            for source_id in ids:
                if source_id not in source_ids:
                    errors.append(f"sections[{index}] references unknown source id: {source_id}")

    if data.get("evidence_mode") == "actual":
        overview_ids = data.get("overview", {}).get("source_ids", [])
        if not overview_ids:
            errors.append("overview needs source_ids in actual mode")
        for source_id in overview_ids:
            if source_id not in source_ids:
                errors.append(f"overview references unknown source id: {source_id}")
    map_path = str(data.get("target", {}).get("map_image_path", ""))
    if map_path:
        map_source_id = str(data.get("target", {}).get("map_source_id", ""))
        if not map_source_id:
            errors.append("target.map_source_id is required when map_image_path is used")
        elif map_source_id not in source_ids:
            errors.append(f"target.map_source_id references unknown source id: {map_source_id}")

    for index, source in enumerate(data.get("sources", []), start=1):
        for key in ("grade", "name", "url", "as_of", "scope", "limitation"):
            if not str(source.get(key, "")).strip():
                errors.append(f"sources[{index}] missing {key}")
        url = str(source.get("url", ""))
        if data.get("evidence_mode") == "actual" and not (
            url.startswith("https://")
            or url.startswith("http://")
            or url == "내부 확인 기록 · 외부 링크 없음"
        ):
            errors.append(f"sources[{index}] needs an original URL or the internal-record label")

    if data.get("evidence_mode") == "actual" and "교육용 가상" in serialized:
        errors.append("actual mode cannot contain educational fictional-data labels")
    audit = audit_request(data, Path(data.get("_base_dir", ".")))
    data["_evidence_audit"] = audit
    data["release_status"] = audit["derived_release_status"]
    for error in audit["errors"]:
        if error not in errors:
            errors.append(error)
    return errors


def local_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def image_data_uri(value: str, base_dir: Path) -> str:
    if not value:
        return ""
    path = local_path(value, base_dir).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def scale(value: float, lo: float, hi: float, start: float, end: float) -> float:
    if hi <= lo:
        return (start + end) / 2
    return start + (float(value) - lo) / (hi - lo) * (end - start)


def fmt_number(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def band_chart(spec: dict[str, Any]) -> str:
    lo, hi = float(spec["min"]), float(spec["max"])
    values = [float(v) for v in spec.get("values", [])]
    target = float(spec["target"])
    x0, x1 = 70.0, 710.0
    ticks = []
    for i in range(6):
        value = lo + (hi - lo) * i / 5
        x = scale(value, lo, hi, x0, x1)
        ticks.append(
            f'<line x1="{x:.1f}" y1="75" x2="{x:.1f}" y2="235" class="gridline"/>'
            f'<text x="{x:.1f}" y="260" text-anchor="middle" class="tick">{esc(fmt_number(value))}</text>'
        )
    dots = []
    for index, value in enumerate(values):
        x = scale(value, lo, hi, x0, x1)
        y = 175 - (index % 3) * 22
        dots.append(f'<circle cx="{x:.1f}" cy="{y}" r="6" class="dot"/>')
    range_svg = ""
    if spec.get("range"):
        r0, r1 = [float(v) for v in spec["range"]]
        rx0, rx1 = scale(r0, lo, hi, x0, x1), scale(r1, lo, hi, x0, x1)
        range_svg = (
            f'<line x1="{rx0:.1f}" y1="105" x2="{rx1:.1f}" y2="105" class="ask-range"/>'
            f'<text x="{(rx0 + rx1) / 2:.1f}" y="88" text-anchor="middle" class="legend">{esc(spec.get("range_label", "공개 범위"))}</text>'
        )
    tx = scale(target, lo, hi, x0, x1)
    return f"""
    <svg viewBox="0 0 780 300" role="img" aria-label="가격 위치 비교">
      {''.join(ticks)}
      <line x1="70" y1="190" x2="710" y2="190" class="axisline"/>
      {range_svg}{''.join(dots)}
      <line x1="{tx:.1f}" y1="58" x2="{tx:.1f}" y2="223" class="target-line"/>
      <circle cx="{tx:.1f}" cy="190" r="11" class="target-dot"/>
      <rect x="{max(76, min(575, tx - 72)):.1f}" y="30" width="144" height="28" rx="14" class="target-pill"/>
      <text x="{max(148, min(647, tx)):.1f}" y="49" text-anchor="middle" class="pill-text">{esc(spec.get("target_label", fmt_number(target)))}</text>
      <text x="390" y="288" text-anchor="middle" class="axis-title">{esc(spec.get("unit", ""))}</text>
    </svg>"""


def bar_chart(spec: dict[str, Any]) -> str:
    rows = spec.get("rows", [])
    max_value = float(spec.get("max") or max(float(row.get("value", 0)) for row in rows) or 1)
    height = max(280, 55 * len(rows) + 45)
    items = []
    for index, row in enumerate(rows):
        value = float(row.get("value", 0))
        y = 34 + index * 55
        width = max(0, min(455, value / max_value * 455))
        fill_class = "bar accent-bar" if row.get("highlight") else "bar"
        items.extend(
            [
                f'<text x="42" y="{y + 18}" class="label">{esc(row.get("label", ""))}</text>',
                f'<rect x="205" y="{y}" width="455" height="25" rx="12" class="bar-bg"/>',
                f'<rect x="205" y="{y}" width="{width:.1f}" height="25" rx="12" class="{fill_class}"/>',
                f'<text x="{min(706, 216 + width):.1f}" y="{y + 18}" class="value">{esc(row.get("display", fmt_number(value)))}</text>',
                f'<text x="205" y="{y + 43}" class="small-label">{esc(row.get("note", ""))}</text>',
            ]
        )
    return f'<svg viewBox="0 0 760 {height}" role="img" aria-label="항목별 비교 막대그래프">{"".join(items)}</svg>'


def line_chart(spec: dict[str, Any]) -> str:
    labels = [str(v) for v in spec.get("labels", [])]
    series = spec.get("series", [])
    numeric = [float(v) for item in series for v in item.get("values", []) if v is not None]
    if len(labels) < 2 or not numeric:
        return '<div class="no-data">자료 부족</div>'
    lo = float(spec.get("min", min(numeric)))
    hi = float(spec.get("max", max(numeric)))
    if math.isclose(lo, hi):
        lo, hi = lo - 1, hi + 1
    x0, x1, y0, y1 = 70.0, 710.0, 230.0, 55.0
    grid = []
    for i in range(5):
        value = lo + (hi - lo) * i / 4
        y = scale(value, lo, hi, y0, y1)
        grid.append(
            f'<line x1="70" y1="{y:.1f}" x2="710" y2="{y:.1f}" class="gridline"/>'
            f'<text x="58" y="{y + 4:.1f}" text-anchor="end" class="tick">{esc(fmt_number(value))}</text>'
        )
    xlabels = []
    for index, label in enumerate(labels):
        x = scale(index, 0, len(labels) - 1, x0, x1)
        xlabels.append(f'<text x="{x:.1f}" y="260" text-anchor="middle" class="tick">{esc(label)}</text>')
    colors = ["#2c61ef", "#ef6a4a", "#1d875f", "#7b61c9"]
    shapes = []
    legends = []
    for s_index, item in enumerate(series):
        color = colors[s_index % len(colors)]
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for index, raw in enumerate(item.get("values", [])):
            if raw is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append((scale(index, 0, len(labels) - 1, x0, x1), scale(float(raw), lo, hi, y0, y1)))
        if current:
            segments.append(current)
        for segment in segments:
            if len(segment) >= 2:
                points = " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
                shapes.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>')
            for x, y in segment:
                shapes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="#fff" stroke-width="2"/>')
        legends.append(f'<circle cx="{505 + s_index * 92}" cy="24" r="5" fill="{color}"/><text x="{516 + s_index * 92}" y="28" class="legend">{esc(item.get("name", ""))}</text>')
    return f'<svg viewBox="0 0 780 285" role="img" aria-label="기간별 추이 그래프">{"".join(grid + xlabels + shapes + legends)}</svg>'


def scatter_chart(spec: dict[str, Any]) -> str:
    points = spec.get("points", [])
    if not points:
        return '<div class="no-data">자료 부족</div>'
    xs = [float(item["x"]) for item in points]
    ys = [float(item["y"]) for item in points]
    lo_x, hi_x = float(spec.get("min_x", min(xs))), float(spec.get("max_x", max(xs)))
    lo_y, hi_y = float(spec.get("min_y", min(ys))), float(spec.get("max_y", max(ys)))
    if math.isclose(lo_x, hi_x):
        lo_x, hi_x = lo_x - 1, hi_x + 1
    if math.isclose(lo_y, hi_y):
        lo_y, hi_y = lo_y - 1, hi_y + 1
    grid = []
    for i in range(5):
        x_value = lo_x + (hi_x - lo_x) * i / 4
        y_value = lo_y + (hi_y - lo_y) * i / 4
        x = scale(x_value, lo_x, hi_x, 78, 710)
        y = scale(y_value, lo_y, hi_y, 230, 55)
        grid.append(f'<line x1="{x:.1f}" y1="55" x2="{x:.1f}" y2="230" class="gridline"/><text x="{x:.1f}" y="256" text-anchor="middle" class="tick">{esc(fmt_number(x_value))}</text>')
        grid.append(f'<line x1="78" y1="{y:.1f}" x2="710" y2="{y:.1f}" class="gridline"/><text x="64" y="{y + 4:.1f}" text-anchor="end" class="tick">{esc(fmt_number(y_value))}</text>')
    nodes = []
    for item in points:
        x = scale(float(item["x"]), lo_x, hi_x, 78, 710)
        y = scale(float(item["y"]), lo_y, hi_y, 230, 55)
        cls = "target-dot" if item.get("highlight") else "dot"
        radius = 10 if item.get("highlight") else 6
        nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" class="{cls}"/><text x="{x + 10:.1f}" y="{y - 10:.1f}" class="small-label">{esc(item.get("label", ""))}</text>')
    return f'<svg viewBox="0 0 780 292" role="img" aria-label="조건 조합 산점도">{"".join(grid + nodes)}<text x="394" y="285" text-anchor="middle" class="axis-title">{esc(spec.get("x_label", ""))}</text><text x="18" y="145" transform="rotate(-90 18 145)" text-anchor="middle" class="axis-title">{esc(spec.get("y_label", ""))}</text></svg>'


def matrix_chart(spec: dict[str, Any]) -> str:
    rows = spec.get("rows", [])
    height = max(280, 55 * len(rows) + 25)
    items = []
    for index, row in enumerate(rows):
        y = 20 + index * 55
        status = str(row.get("status", "판단 보류"))
        status_class = STATUS_LABELS.get(status, "hold")
        items.extend(
            [
                f'<rect x="35" y="{y}" width="690" height="43" rx="10" class="matrix-row"/>',
                f'<text x="53" y="{y + 27}" class="label">{esc(row.get("label", ""))}</text>',
                f'<rect x="250" y="{y + 9}" width="100" height="25" rx="12" class="status {status_class}"/>',
                f'<text x="300" y="{y + 26}" text-anchor="middle" class="status-text">{esc(status)}</text>',
                f'<text x="368" y="{y + 26}" class="small-label">{esc(row.get("note", ""))}</text>',
            ]
        )
    return f'<svg viewBox="0 0 760 {height}" role="img" aria-label="조건 확인표">{"".join(items)}</svg>'


def image_visual(spec: dict[str, Any], base_dir: Path) -> str:
    uri = image_data_uri(str(spec.get("path", "")), base_dir)
    if not uri:
        return '<div class="no-data">이미지 확인 필요</div>'
    return f'<img class="evidence-image" src="{uri}" alt="{esc(spec.get("alt", "현장 또는 지도 이미지"))}">'


def render_visual(spec: dict[str, Any], base_dir: Path) -> str:
    visual_type = spec.get("type")
    return {
        "band": lambda: band_chart(spec),
        "bar": lambda: bar_chart(spec),
        "line": lambda: line_chart(spec),
        "scatter": lambda: scatter_chart(spec),
        "matrix": lambda: matrix_chart(spec),
        "image": lambda: image_visual(spec, base_dir),
    }[visual_type]()


def demo_badge(data: dict[str, Any]) -> str:
    if data.get("evidence_mode") == "demo":
        return '<div class="demo-badge">교육용 예시 · 실제 시세가 아님</div>'
    return ""


def generic_hero(mode: str) -> str:
    if mode == "land_lease":
        return """
        <svg viewBox="0 0 1200 700" role="img" aria-label="토지 위치 일러스트">
          <rect width="1200" height="700" fill="#dbe9e1"/><path d="M0 470L330 340l350 60 520-150v450H0z" fill="#9fbea3"/>
          <path d="M0 630C250 490 470 585 690 455c215-126 320-40 510-110" fill="none" stroke="#f7f5ef" stroke-width="88"/>
          <path d="M370 150l420-35 130 255-400 55z" fill="#2c61ef" opacity=".75" stroke="#fff" stroke-width="10"/>
          <circle cx="650" cy="245" r="50" fill="#fff"/><path d="M650 165c-47 0-85 38-85 85 0 66 85 150 85 150s85-84 85-150c0-47-38-85-85-85zm0 116a32 32 0 1 1 0-64 32 32 0 0 1 0 64z" fill="#183f91"/>
        </svg>"""
    if mode == "commercial_lease":
        return """
        <svg viewBox="0 0 1200 700" role="img" aria-label="상가 건물 일러스트">
          <rect width="1200" height="700" fill="#dfe7f7"/><rect y="560" width="1200" height="140" fill="#c9d2df"/>
          <rect x="170" y="80" width="860" height="490" rx="12" fill="#f7f8fb"/>
          <g fill="#b9c8dc"><rect x="225" y="140" width="180" height="135"/><rect x="435" y="140" width="180" height="135"/><rect x="645" y="140" width="180" height="135"/><rect x="855" y="140" width="120" height="135"/></g>
          <rect x="225" y="330" width="270" height="240" fill="#2c61ef"/><rect x="525" y="330" width="210" height="240" fill="#233c72"/><rect x="765" y="330" width="210" height="240" fill="#8fa4c4"/>
          <rect x="270" y="385" width="180" height="125" fill="#eff5ff"/><text x="360" y="462" text-anchor="middle" font-size="42" font-weight="800" fill="#16345e">SHOP</text>
        </svg>"""
    return """
    <svg viewBox="0 0 1200 700" role="img" aria-label="주거 건물 일러스트">
      <rect width="1200" height="700" fill="#dce6f2"/><rect y="560" width="1200" height="140" fill="#cad3df"/>
      <rect x="160" y="85" width="270" height="500" fill="#f8fafc"/><rect x="465" y="45" width="285" height="540" fill="#eef2f7"/><rect x="785" y="115" width="245" height="470" fill="#f8fafc"/>
      <g fill="#9fb4cd"><rect x="205" y="140" width="55" height="70"/><rect x="315" y="140" width="55" height="70"/><rect x="205" y="255" width="55" height="70"/><rect x="315" y="255" width="55" height="70"/><rect x="205" y="370" width="55" height="70"/><rect x="315" y="370" width="55" height="70"/><rect x="515" y="105" width="70" height="80"/><rect x="635" y="105" width="70" height="80"/><rect x="515" y="235" width="70" height="80"/><rect x="635" y="235" width="70" height="80"/><rect x="515" y="365" width="70" height="80"/><rect x="635" y="365" width="70" height="80"/><rect x="830" y="175" width="55" height="70"/><rect x="930" y="175" width="55" height="70"/><rect x="830" y="290" width="55" height="70"/><rect x="930" y="290" width="55" height="70"/></g>
      <path d="M0 620h1200" stroke="#fff" stroke-width="12"/><circle cx="1080" cy="535" r="55" fill="#789b79"/><rect x="1072" y="535" width="16" height="75" fill="#6d6254"/>
    </svg>"""


def page_footer(brand: str, page: int, total: int) -> str:
    return f'<div class="footer"><span>{esc(brand)}</span><span>{page:02d} / {total:02d}</span></div>'


def paragraphs(items: list[str]) -> str:
    return "".join(f'<p class="copy">{esc(item)}</p>' for item in items)


def source_line(section: dict[str, Any], data: dict[str, Any]) -> str:
    claim_map = {str(item.get("id")): item for item in data.get("claims", [])}
    ids: list[str] = []
    for claim_id in section.get("claim_ids", []):
        for source_id in claim_map.get(str(claim_id), {}).get("source_ids", []):
            if str(source_id) not in ids:
                ids.append(str(source_id))
    if not ids:
        ids = [str(item) for item in section.get("source_ids", [])]
    if not ids:
        return ""
    source_map = {str(item.get("id")): item for item in data.get("sources", [])}
    chunks = []
    for source_id in ids:
        source = source_map.get(str(source_id), {})
        url = str(source.get("url", ""))
        if url.startswith("http://") or url.startswith("https://"):
            label = f'<a href="{esc(url)}">{esc(source_id)} · {esc(source.get("name", ""))}</a>'
        else:
            label = f'{esc(source_id)} · {esc(source.get("name", ""))}'
        chunks.append(f'{label} · {esc(source.get("as_of", ""))}')
    return '<div class="source-links">출처: ' + " / ".join(chunks) + '</div>'


def render_report(data: dict[str, Any]) -> str:
    base_dir = Path(data["_base_dir"])
    mode_label, _ = MODES[data["mode"]]
    brand = data["brand"]
    brand_name = str(brand["name"])
    color = str(brand.get("color", "#2c61ef"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#2c61ef"
    page_count = 4 + len(data["sections"])
    target = data["target"]
    customer = data["customer"]

    photo_uri = image_data_uri(str(target.get("image_path", "")), base_dir)
    map_uri = image_data_uri(str(target.get("map_image_path", "")), base_dir)
    if photo_uri:
        hero = f'<img src="{photo_uri}" alt="{esc(target.get("name"))} 대상 이미지">'
    else:
        hero = generic_hero(data["mode"])
    source_map = {str(item.get("id")): item for item in data.get("sources", [])}
    map_card = ""
    if map_uri:
        map_link = str(target.get("map_link", ""))
        map_source = source_map.get(str(target.get("map_source_id", "")), {})
        map_label = f"{map_source.get('name', '대상 위치')} · {map_source.get('as_of', data['basis_date'])}"
        open_tag = f'<a href="{esc(map_link)}" class="map-card">' if map_link.startswith("http") else '<div class="map-card">'
        close_tag = "</a>" if open_tag.startswith("<a") else "</div>"
        map_card = f'{open_tag}<img src="{map_uri}" alt="대상 위치 지도"><span>{esc(map_label)}</span>{close_tag}'

    pages: list[str] = []
    pages.append(
        f"""
        <section class="sheet cover">
          {demo_badge(data)}
          <div class="cover-top">
            <p class="cover-kicker">{esc(mode_label)} BRIEF · {esc(customer['role'])}</p>
            <h1>{esc(customer['question'])}</h1>
            <p class="cover-question">{esc(customer['scope'])}</p>
            <div class="cover-target"><b>{esc(target['name'])}</b><span>{esc(target.get('address', ''))}</span><span>{esc(target['descriptor'])} · 기준일 {esc(data['basis_date'])}</span></div>
          </div>
          <div class="cover-visual">{hero}</div>
          {map_card}
          <div class="cover-brand">{esc(brand_name)}</div>
        </section>"""
    )

    metric_html = "".join(
        f'<article class="metric"><span>{esc(item.get("label", ""))}</span><strong>{esc(item.get("value", ""))}</strong><small>{esc(item.get("note", ""))}</small></article>'
        for item in data["metrics"]
    )
    overview = data["overview"]
    pages.append(
        f"""
        <section class="sheet page">
          {demo_badge(data)}
          <p class="part">DECISION OVERVIEW · {esc(mode_label)}</p>
          <h1>{esc(overview['title'])}</h1>
          <div class="metric-grid">{metric_html}</div>
          {paragraphs(overview.get('paragraphs', []))}
          <div class="quote"><b>한눈에 설명</b>{esc(overview['takeaway'])}</div>
          {source_line(overview, data)}
          <div class="basis-box"><b>분석 기준</b><span>{esc(target['name'])} · {esc(target['descriptor'])}</span><span>{esc(data['basis_date'])} · {esc(data['evidence_mode'].upper())}</span></div>
          {page_footer(brand_name, 2, page_count)}
        </section>"""
    )

    for index, section in enumerate(data["sections"], start=3):
        visual = render_visual(section["visual"], base_dir)
        pages.append(
            f"""
            <section class="sheet page">
              {demo_badge(data)}
              <p class="part">{esc(section.get('part', f'PART {index - 2:02d}'))}</p>
              <h1>{esc(section['title'])}</h1>
              <p class="lead">{esc(section['lead'])}</p>
              <figure class="diagram">{visual}</figure>
              <p class="caption">{esc(section['caption'])}</p>
              {source_line(section, data)}
              <h2>{esc(section.get('subtitle', '확인할 부분'))}</h2>
              <p class="copy">{esc(section['body'])}</p>
              <div class="quote"><b>한눈에 설명</b>{esc(section['takeaway'])}</div>
              {page_footer(brand_name, index, page_count)}
            </section>"""
        )

    checklist_page = 3 + len(data["sections"])
    checks = "".join(
        f'<article class="check-item"><b>{esc(item.get("title", ""))}</b><span>{esc(item.get("body", ""))}</span></article>'
        for item in data["checklist"]
    )
    pages.append(
        f"""
        <section class="sheet page">
          {demo_badge(data)}
          <p class="part">CONTRACT CHECK · {esc(mode_label)}</p>
          <h1>계약 전에 무엇을 확인해야 할까요?</h1>
          <p class="lead">아래 항목은 가격이나 조건의 해석을 바꿀 수 있으므로 계약 직전에 다시 확인합니다.</p>
          <div class="check-list">{checks}</div>
          <div class="notice">확인되지 않은 권리·보증·허가·용도·현장조건은 계약서와 특약, 공식기관 또는 현장 확인을 통해 보완해야 합니다.</div>
          {page_footer(brand_name, checklist_page, page_count)}
        </section>"""
    )

    summary = data["summary"]
    cards = "".join(
        f'<article class="action"><b>{esc(item.get("title", ""))}</b><span>{esc(item.get("body", ""))}</span></article>'
        for item in summary["cards"]
    )
    contact_bits = [str(brand.get("agent_name", "")).strip(), str(brand.get("contact", "")).strip()]
    contact = " · ".join(item for item in contact_bits if item)
    pages.append(
        f"""
        <section class="sheet closing">
          {demo_badge(data)}
          <p class="part">FINAL BRIEF · {esc(customer['role'])}</p>
          <h1>이번 분석을<br>정리하면</h1>
          <div class="closing-summary">{paragraphs(summary.get('paragraphs', []))}</div>
          <div class="actions">{cards}</div>
          <div class="closing-source">기준일 {esc(data['basis_date'])} · {esc(data['release_status'])}</div>
          <div class="closing-brand">{esc(brand_name)}{(' · ' + esc(contact)) if contact else ''}</div>
          <div class="closing-disclaimer">{esc(data['disclaimer'])}</div>
        </section>"""
    )

    audit = data.get("_evidence_audit") or audit_request(data, base_dir)
    fingerprint = str(audit.get("evidence_fingerprint", ""))
    release_status = str(audit.get("derived_release_status", data.get("release_status", "HOLD")))
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="evidence-audit-sha256" content="{esc(fingerprint)}">
<meta name="derived-release-status" content="{esc(release_status)}">
<title>{esc(target['name'])} · {esc(mode_label)} 고객 브리핑</title>
<style>
:root{{--blue:{color};--blue-dark:#153f9d;--ink:#17191d;--muted:#6e7580;--line:#d8dde5;--soft:#f4f7fb;--accent:#ef6a4a;--green:#1d875f}}
*{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:#dfe4ec;color:var(--ink)}}body{{font-family:"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif}}
@page{{size:A4;margin:0}}@media print{{html,body{{background:#fff}}.sheet{{margin:0!important;box-shadow:none!important}}}}
.sheet{{position:relative;width:210mm;height:297mm;margin:8mm auto;overflow:hidden;background:#fff;box-shadow:0 4mm 14mm rgba(20,38,70,.13);break-after:page;page-break-after:always}}.sheet:last-child{{break-after:auto;page-break-after:auto}}
.demo-badge{{position:absolute;right:12mm;top:9mm;z-index:10;padding:2mm 4mm;border-radius:99px;background:#fff1c9;color:#754b00;font-size:6.4pt;font-weight:900;box-shadow:0 1mm 3mm rgba(0,0,0,.08)}}
.cover-top{{height:156mm;padding:18mm 18mm 12mm;background:var(--blue);color:#fff}}.cover-kicker{{margin:0 0 7mm;font-size:9pt;font-weight:900;letter-spacing:.03em}}.cover h1{{max-width:165mm;margin:0;font-size:34pt;line-height:1.12;letter-spacing:-.06em;word-break:keep-all}}.cover-question{{max-width:158mm;margin:9mm 0 0;font-size:11pt;line-height:1.58;font-weight:700;word-break:keep-all}}.cover-target{{display:grid;gap:1.4mm;margin-top:10mm;font-size:7.4pt;color:rgba(255,255,255,.82)}}.cover-target b{{font-size:10pt;color:#fff}}
.cover-visual{{height:141mm;overflow:hidden;background:#dce5f4}}.cover-visual img,.cover-visual svg{{display:block;width:100%;height:100%;object-fit:cover}}.map-card{{position:absolute;right:14mm;bottom:20mm;width:58mm;height:45mm;overflow:hidden;border:1.2mm solid #fff;border-radius:3mm;background:#fff;color:#32405a;text-decoration:none;box-shadow:0 3mm 9mm rgba(12,27,60,.25)}}.map-card img{{width:100%;height:36mm;object-fit:cover;display:block}}.map-card span{{display:block;padding:1.4mm 2mm;font-size:5.6pt;font-weight:700}}.cover-brand{{position:absolute;left:16mm;bottom:10mm;color:#fff;font-size:10pt;font-weight:900;text-shadow:0 1px 3px rgba(0,0,0,.25)}}
.page{{padding:18mm 18mm 17mm}}.page::after{{content:"{esc(brand_name)}";position:absolute;left:52mm;top:150mm;color:#17275a;opacity:.025;font-size:42pt;font-weight:900;transform:rotate(-32deg)}}.page>*{{position:relative;z-index:1}}.page>.demo-badge{{position:absolute;right:12mm;top:8mm;width:auto;z-index:10}}.part{{margin:0 0 3mm;font-size:7.2pt;font-weight:900;letter-spacing:.04em}}.page h1{{margin:0 0 8mm;color:var(--blue);font-size:23pt;line-height:1.2;letter-spacing:-.055em;word-break:keep-all}}.page h2{{margin:5mm 0 3mm;color:var(--blue);font-size:13pt;letter-spacing:-.04em}}.lead,.copy{{font-size:9.5pt;line-height:1.78;letter-spacing:-.02em;word-break:keep-all}}.lead{{margin:0 0 5mm}}.copy{{margin:0 0 3.5mm}}
.metric-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin:0 0 9mm}}.metric{{min-height:29mm;padding:4mm;border:.3mm solid var(--line);border-radius:3mm;background:#fff}}.metric span{{display:block;margin-bottom:2mm;color:var(--muted);font-size:6.7pt}}.metric strong{{display:block;color:var(--blue-dark);font-size:14pt;letter-spacing:-.04em}}.metric small{{font-size:6pt;color:var(--muted)}}.basis-box{{display:grid;gap:1.5mm;margin-top:8mm;padding:5mm;border-radius:3mm;background:#f2f5fa;color:#59616d;font-size:7.5pt}}.basis-box b{{color:var(--blue-dark);font-size:9pt}}
.diagram{{height:88mm;margin:0 0 2mm;padding:3mm;border:.3mm solid var(--line);border-radius:3mm;background:#fff}}.diagram svg,.evidence-image{{display:block;width:100%;height:100%;object-fit:contain}}.caption{{margin:0 0 2mm;color:#7b818a;font-size:6.3pt;line-height:1.45}}.source-links{{margin:0 0 4mm;color:#647089;font-size:6pt;line-height:1.45}}.source-links a{{color:#2454be;text-decoration:underline}}
.quote{{margin:5mm 0 0;padding:4mm 5mm;border-left:1.5mm solid var(--blue);background:#f5f8ff;font-size:9pt;line-height:1.68;font-weight:700;word-break:keep-all}}.quote b{{display:block;margin-bottom:1.5mm;color:var(--blue);font-size:7.5pt}}
.check-list{{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-top:6mm}}.check-item{{min-height:28mm;padding:4mm;border:.3mm solid var(--line);border-radius:2.5mm;background:#fff}}.check-item b{{display:block;margin-bottom:1.5mm;color:var(--blue-dark);font-size:8.5pt}}.check-item span{{display:block;color:#4d535c;font-size:7.4pt;line-height:1.52;word-break:keep-all}}.notice{{margin-top:5mm;padding:4mm;border-radius:2mm;background:#fff4ea;color:#6f3b20;font-size:7.2pt;line-height:1.55}}
.footer{{position:absolute;left:18mm;right:18mm;bottom:7mm;display:flex;justify-content:space-between;color:#7a8088;font-size:6.2pt}}.no-data{{display:flex;height:100%;align-items:center;justify-content:center;color:#7a818b;font-weight:800}}
.closing{{padding:20mm 18mm;background:var(--blue);color:#fff}}.closing .part{{color:#fff}}.closing h1{{margin:0 0 12mm;color:#fff;font-size:28pt;line-height:1.18;letter-spacing:-.06em}}.closing-summary{{padding:7mm;border:.35mm solid rgba(255,255,255,.48);border-radius:3mm;background:rgba(255,255,255,.07)}}.closing-summary .copy{{margin:0 0 5mm;font-size:10.5pt;line-height:1.75}}.closing-summary .copy:last-child{{margin:0}}.actions{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:10mm}}.action{{min-height:39mm;padding:5mm 4mm;border-radius:2mm;background:#fff;color:#18325f}}.action b{{display:block;margin-bottom:2mm;font-size:8pt}}.action span{{font-size:7.4pt;line-height:1.5;word-break:keep-all}}.closing-source{{margin-top:6mm;font-size:6.5pt;color:rgba(255,255,255,.78)}}.closing-brand{{position:absolute;left:18mm;bottom:15mm;font-size:10pt;font-weight:900}}.closing-disclaimer{{position:absolute;right:18mm;bottom:14mm;width:120mm;text-align:right;font-size:5.5pt;line-height:1.4;color:rgba(255,255,255,.75)}}
.gridline{{stroke:#e5e8ee;stroke-width:1}}.axisline{{stroke:#bac2ce;stroke-width:1.4}}.tick,.small-label{{fill:#727984;font-size:12px}}.label{{fill:#27303b;font-size:14px;font-weight:700}}.axis-title{{fill:#626a75;font-size:13px}}.value{{fill:#173c88;font-size:13px;font-weight:900}}.dot{{fill:var(--blue)}}.target-dot{{fill:var(--accent);stroke:#fff;stroke-width:4}}.target-line{{stroke:var(--accent);stroke-width:2;stroke-dasharray:7 5}}.target-pill{{fill:var(--accent)}}.pill-text{{fill:#fff;font-size:11px;font-weight:900}}.ask-range{{stroke:var(--accent);stroke-width:12;stroke-linecap:round}}.legend{{fill:#57606c;font-size:12px}}.bar{{fill:var(--blue)}}.accent-bar{{fill:var(--accent)}}.bar-bg{{fill:#e8edf5}}.matrix-row{{fill:#f7f9fc;stroke:#d9dee7}}.status.ok{{fill:#dff3e9}}.status.warn{{fill:#fff0cf}}.status.hold{{fill:#ffe2df}}.status-text{{fill:#26323d;font-size:11px;font-weight:900}}
</style>
</head>
<body>
{''.join(pages)}
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an EZIWORK-style customer real-estate briefing HTML.")
    parser.add_argument("input", type=Path, help="Path to report request JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output HTML path")
    parser.add_argument("--audit-output", type=Path, help="Optional evidence audit JSON path")
    args = parser.parse_args()
    data = load_request(args.input)
    errors = validate_request(data)
    audit = data.get("_evidence_audit", {})
    if args.audit_output:
        write_audit(audit, args.audit_output)
    for warning in audit.get("warnings", []):
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    if audit.get("derived_release_status") == RELEASE_HOLD:
        print("ERROR: derived release status is HOLD; customer HTML was not created")
        return 2
    rendered = render_report(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
