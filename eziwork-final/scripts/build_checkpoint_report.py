from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

from build_report import esc, image_data_uri, load_request, validate_request
from evidence_audit import RELEASE_HOLD, write_audit


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = SKILL_ROOT / "assets" / "checkpoint-editorial-reference.html"
CHART_IDS = ("chart-consulting", "chart-scatter", "chart-monthly", "chart-competition")


def rich(value: Any) -> str:
    """Escape text and support only **bold** editorial emphasis."""
    safe = esc(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)


def title_lines(values: Any) -> str:
    lines = values if isinstance(values, list) else [values]
    return "<br>".join(esc(line) for line in lines if str(line).strip())


def optional_heading(values: Any) -> str:
    rendered = title_lines(values)
    return f"<h1>{rendered}</h1>" if rendered else ""


def paragraph_block(values: list[Any], class_name: str = "body-copy") -> str:
    return "".join(f'<p class="{class_name}">{rich(value)}</p>' for value in values)


def footer(page: int, brand: str, target: str) -> str:
    return (
        '<footer class="editorial-footer">'
        f'<span>{esc(brand)} 매물 의사결정 브리핑&nbsp;&nbsp;|&nbsp;&nbsp;{esc(target)}</span>'
        f'<b>{page:02d}</b></footer>'
    )


def demo_badge(is_demo: bool) -> str:
    if not is_demo:
        return ""
    return '<div class="demo-badge">교육용 예시 · 실제 시세가 아님</div>'


def placeholder_uri(label: str, kind: str) -> str:
    subtitle = "BUILDING IMAGE" if kind == "photo" else "STATIC MAP"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
    <rect width="1200" height="800" fill="#dfe7f7"/><path d="M0 690L290 410l170 150 250-270 490 400v110H0z" fill="#9bb2dc"/>
    <circle cx="935" cy="170" r="75" fill="#ef6a4a" opacity=".8"/><text x="70" y="105" font-family="sans-serif" font-size="32" fill="#1742a6">{esc(subtitle)}</text>
    <text x="70" y="175" font-family="sans-serif" font-size="48" font-weight="700" fill="#1742a6">{esc(label)}</text></svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def image_uri(target: dict[str, Any], key: str, base_dir: Path, is_demo: bool) -> str:
    value = str(target.get(key, "")).strip()
    if value:
        return image_data_uri(value, base_dir)
    if not is_demo:
        raise ValueError(f"actual report requires target.{key}")
    kind = "map" if "map" in key else "photo"
    return placeholder_uri(str(target.get("name", "교육용 대상")), kind)


def require_checkpoint(data: dict[str, Any], route: str) -> list[str]:
    errors: list[str] = []
    cp = data.get("checkpoint_report")
    if not isinstance(cp, dict):
        return ["checkpoint_report object is required"]
    if route not in {"BUY", "SELL"}:
        errors.append("customer_type must be BUY or SELL")
    if cp.get("customer_type") and cp.get("customer_type") != route:
        errors.append("checkpoint_report.customer_type does not match --customer-type")
    if len(cp.get("prologue_pages", [])) != 2:
        errors.append("checkpoint_report.prologue_pages must contain exactly 2 pages")
    analyses = cp.get("analysis_pages", [])
    if len(analyses) != 4:
        errors.append("checkpoint_report.analysis_pages must contain exactly 4 pages")
    else:
        ids = tuple(page.get("chart_id") for page in analyses)
        if ids != CHART_IDS:
            errors.append("analysis chart_id order must be: " + ", ".join(CHART_IDS))
    if len(cp.get("closing", {}).get("paragraphs", [])) != 5:
        errors.append("checkpoint_report.closing.paragraphs must contain exactly 5 paragraphs")
    chart = cp.get("chart_data", {})
    for key in ("trades", "months", "asks", "reference", "review", "askMin", "askMax"):
        if key not in chart:
            errors.append(f"checkpoint_report.chart_data missing {key}")
    return errors


def source_note(data: dict[str, Any], page: dict[str, Any]) -> str:
    explicit = str(page.get("source_note", "")).strip()
    if explicit:
        return rich(explicit)
    index = {str(item.get("id")): item for item in data.get("sources", [])}
    labels = []
    for source_id in page.get("source_ids", []):
        item = index.get(str(source_id))
        if item:
            labels.append(f'{item.get("name", source_id)} · {item.get("as_of", data.get("basis_date", ""))}')
    return esc(" / ".join(labels) or f'기준일 {data.get("basis_date", "")}')


def render_fact_table(facts: list[dict[str, Any]]) -> str:
    cells = []
    for item in facts[:4]:
        cells.append(f'<th>{esc(item.get("label", ""))}</th><td>{esc(item.get("value", ""))}</td>')
    rows = []
    for index in range(0, len(cells), 4):
        rows.append("<tr>" + "".join(cells[index:index + 4]) + "</tr>")
    return '<table class="fact-table">' + "".join(rows) + "</table>"


def build_body(data: dict[str, Any], route: str, photo_uri: str, map_uri: str) -> str:
    cp = data["checkpoint_report"]
    target = data["target"]
    brand = data["brand"]["name"]
    target_name = target["name"]
    is_demo = data["evidence_mode"] == "demo"
    badge = demo_badge(is_demo)
    cover = cp["cover"]

    parts: list[str] = [f"""
    <section class="sheet cover">{badge}
      <div class="cover-top">
        <p class="cover-kicker">{esc(cover.get('kicker', f'{brand} 매물 의사결정 리포트'))}</p>
        <h1 class="cover-title">{''.join(f'<span>{esc(line)}</span>' for line in cover.get('title_lines', [target_name, '분석 리포트']))}</h1>
        <p class="cover-type">{esc(cover.get('route_label', '매수 검토' if route == 'BUY' else '매도 전략'))} · {esc(brand)}</p>
      </div>
      <figure class="cover-photo"><img src="{photo_uri}" alt="{esc(target_name)} 외관"><figcaption>{rich(cover.get('image_credit', '이미지 출처와 기준일을 입력하세요.'))}</figcaption></figure>
    </section>"""]

    for page_no, page in enumerate(cp["prologue_pages"], start=2):
        parts.append(f"""
        <section class="sheet page intro">{badge}
          <p class="part">{esc(page.get('part', '프롤로그'))}</p>
          {optional_heading(page.get('title_lines', []))}
          {paragraph_block(page.get('paragraphs', []))}
          <img class="city-fade" src="{photo_uri}" alt="">
          {footer(page_no, brand, target_name)}
        </section>""")

    prop = cp["property_page"]
    parts.append(f"""
    <section class="sheet page">{badge}
      <p class="part">{esc(prop.get('part', 'PART 1. 어디에 있는 매물인가'))}</p>
      <h1>{title_lines(prop.get('title_lines', [target_name]))}</h1>
      <div class="checkpoint"><b>CHECK POINT!</b><span>{rich(prop.get('checkpoint', target.get('descriptor', '')))}</span></div>
      <figure class="map-frame"><img src="{map_uri}" alt="{esc(target_name)} 위치 지도"></figure>
      <p class="caption">{rich(prop.get('map_caption', '지도 출처와 기준일을 입력하세요.'))}</p>
      {paragraph_block(prop.get('paragraphs', []))}
      {render_fact_table(prop.get('facts', []))}
      <p class="source-note">{source_note(data, prop)}</p>
      {footer(4, brand, target_name)}
    </section>""")

    for offset, page in enumerate(cp["analysis_pages"], start=5):
        size = "compact" if offset == 5 else "tall"
        parts.append(f"""
        <section class="sheet page">{badge}
          <p class="part">{esc(page.get('part', ''))}</p>
          <h1>{title_lines(page.get('title_lines', []))}</h1>
          <div class="chart-frame {size}"><div class="plot" id="{esc(page['chart_id'])}"></div></div>
          <p class="caption">{rich(page.get('caption', ''))}</p>
          <p class="lead">{rich(page.get('lead', ''))}</p>
          <h2>{rich(page.get('subheading', ''))}</h2>
          <p class="body-copy">{rich(page.get('body', ''))}</p>
          <p class="quote"><b>한눈에 설명</b><br>{rich(page.get('takeaway', ''))}</p>
          <p class="source-note">{source_note(data, page)}</p>
          {footer(offset, brand, target_name)}
        </section>""")

    closing = cp["closing"]
    parts.append(f"""
    <section class="sheet closing">{badge}
      <figure class="closing-photo"><img src="{photo_uri}" alt="{esc(target_name)} 외관"></figure>
      <div class="closing-copy">{paragraph_block(closing['paragraphs'], 'closing-paragraph')}</div>
      <div class="closing-line"></div><div class="closing-brand">{esc(brand)}</div>
    </section>""")
    return "".join(parts)


def build_html(data: dict[str, Any], route: str, request_path: Path) -> str:
    reference = REFERENCE.read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", reference, re.S)
    if not css:
        raise ValueError("golden HTML style block not found")
    tail_start = reference.index('<div class="tooltip"')
    tail_end = reference.rindex("</body>")
    script_tail = reference[tail_start:tail_end]
    chart_json = json.dumps(data["checkpoint_report"]["chart_data"], ensure_ascii=False)
    script_tail, count = re.subn(
        r'(<script id="report-data" type="application/json">).*?(</script>)',
        lambda match: match.group(1) + chart_json + match.group(2),
        script_tail,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("golden HTML report-data block not found")
    base_dir = request_path.resolve().parent
    is_demo = data["evidence_mode"] == "demo"
    photo_uri = image_uri(data["target"], "image_path", base_dir, is_demo)
    map_uri = image_uri(data["target"], "map_image_path", base_dir, is_demo)
    body = build_body(data, route, photo_uri, map_uri)
    extra_css = """
    .demo-badge{position:absolute;top:5mm;right:6mm;z-index:30;padding:1.8mm 3mm;border-radius:99mm;background:#ef6a4a;color:#fff;font-size:6.5pt;font-weight:900}
    .closing-paragraph{margin:0 0 7mm;font-size:12pt;line-height:1.85;letter-spacing:-.025em}.closing-paragraph strong{font-weight:900}
    """
    title = f'{data["target"]["name"]} {route} 시세 분석 리포트'
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css.group(1)}{extra_css}</style></head><body>{body}{script_tail}</body></html>'


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canonical nine-page BUY/SELL checkpoint report")
    parser.add_argument("request", type=Path)
    parser.add_argument("--customer-type", choices=("BUY", "SELL"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    data = load_request(args.request)
    errors = validate_request(data)
    errors.extend(require_checkpoint(data, args.customer_type))
    audit = data.get("_evidence_audit", {})
    write_audit(audit, args.audit_output)
    if audit.get("derived_release_status") == RELEASE_HOLD:
        errors.append("audit-derived release status is HOLD; customer HTML is refused")
    if errors:
        for error in dict.fromkeys(errors):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    html = build_html(data, args.customer_type, args.request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
