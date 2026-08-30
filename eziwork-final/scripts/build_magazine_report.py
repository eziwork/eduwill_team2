from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from build_report import (
    MODES,
    RELEASE_HOLD,
    esc,
    image_data_uri,
    load_request,
    page_footer,
    paragraphs,
    render_visual,
    source_line,
    validate_request,
    write_audit,
)


def magazine_badge(data: dict[str, Any]) -> str:
    if data.get("evidence_mode") == "demo":
        return '<span class="mag-demo">교육용 재구성 · 현재 시세가 아님</span>'
    return ""


def evidence_note(section: dict[str, Any], data: dict[str, Any]) -> str:
    note = str(section.get("evidence_note", "")).strip()
    source_map = {str(item.get("id")): item for item in data.get("sources", [])}
    chunks: list[str] = []
    for source_id in section.get("source_ids", []):
        source = source_map.get(str(source_id), {})
        url = str(source.get("url", ""))
        name = esc(source.get("name", source_id))
        label = f'<a href="{esc(url)}">{name}</a>' if url.startswith(("http://", "https://")) else name
        chunks.append(f'{label} · {esc(source.get("as_of", ""))} · {esc(source.get("scope", ""))}')
    sources = '<div class="source-links"><b>근거</b> ' + " / ".join(chunks) + "</div>" if chunks else source_line(section, data)
    return f'{sources}<p class="evidence-note"><b>한계</b> {esc(note)}</p>'


def render_section(section: dict[str, Any], data: dict[str, Any], page: int, total: int) -> str:
    base_dir = Path(data["_base_dir"])
    brand_name = str(data["brand"]["name"])
    layout = str(section.get("layout", "chart"))
    visual = render_visual(section["visual"], base_dir)
    common_head = f"""
      {magazine_badge(data)}
      <p class="part">{esc(section.get('part', f'CHAPTER {page:02d}'))}</p>
      <h1>{esc(section['title'])}</h1>
      <p class="lead">{esc(section['lead'])}</p>"""
    sources = evidence_note(section, data)
    footer = page_footer(brand_name, page, total)

    if layout == "prologue":
        return f"""
        <section class="sheet page magazine prologue">
          {magazine_badge(data)}
          <div class="prologue-image"><figure>{visual}</figure></div>
          <div class="prologue-copy">
            <p class="part">{esc(section.get('part', 'PROLOGUE'))}</p>
            <h1>{esc(section['title'])}</h1>
            <p class="lead">{esc(section['lead'])}</p>
            <h2>{esc(section.get('subtitle', '이 단지를 읽는 관점'))}</h2>
            <p class="copy">{esc(section['body'])}</p>
            <div class="pull-quote">{esc(section['takeaway'])}</div>
            <p class="caption">{esc(section['caption'])}</p>{sources}
          </div>{footer}
        </section>"""

    if layout == "map":
        return f"""
        <section class="sheet page magazine layout-map">
          {common_head}
          <figure class="map-frame">{visual}<span class="map-pin">TARGET</span></figure>
          <p class="caption">{esc(section['caption'])}</p>{sources}
          <div class="map-analysis"><h2>{esc(section.get('subtitle', '입지를 읽는 기준'))}</h2><p class="copy">{esc(section['body'])}</p></div>{footer}
        </section>"""

    if layout == "matrix":
        return f"""
        <section class="sheet page magazine layout-matrix">
          {common_head}
          <figure class="diagram matrix-diagram">{visual}</figure>
          <p class="caption">{esc(section['caption'])}</p>{sources}
          <div class="story-grid"><div><h2>{esc(section.get('subtitle', '투자 판단의 균형'))}</h2><p class="copy">{esc(section['body'])}</p></div>
          <aside class="takeaway dark"><b>INVESTMENT VIEW</b>{esc(section['takeaway'])}</aside></div>{footer}
        </section>"""

    return f"""
      <section class="sheet page magazine layout-chart">
        {common_head}
        <figure class="diagram">{visual}</figure>
        <p class="caption">{esc(section['caption'])}</p>{sources}
        <div class="story-grid"><div><h2>{esc(section.get('subtitle', '차트가 말하는 것'))}</h2><p class="copy">{esc(section['body'])}</p></div>
        <aside class="takeaway"><b>KEY READING</b>{esc(section['takeaway'])}</aside></div>{footer}
      </section>"""


def render_report(data: dict[str, Any]) -> str:
    base_dir = Path(data["_base_dir"])
    mode_label, _ = MODES[data["mode"]]
    brand = data["brand"]
    brand_name = str(brand["name"])
    color = str(brand.get("color", "#2658d9"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#2658d9"
    target, customer, overview = data["target"], data["customer"], data["overview"]
    photo_uri = image_data_uri(str(target.get("image_path", "")), base_dir)
    hero = f'<img src="{photo_uri}" alt="{esc(target.get("name"))} 외관">' if photo_uri else ""
    total = 4 + len(data["sections"])
    pages: list[str] = []

    pages.append(f"""
    <section class="sheet cover magazine-cover">
      {magazine_badge(data)}
      <div class="cover-photo">{hero}</div><div class="cover-wash"></div>
      <div class="cover-editorial"><p class="issue">EZIWORK PROPERTY · INVESTMENT BRIEF</p>
      <h1>{esc(target['name'])}</h1><p class="cover-deck">{esc(customer['question'])}</p>
      <div class="cover-rule"></div><p class="cover-meta">{esc(target['descriptor'])}<br>{esc(target.get('address', ''))}<br>기준일 {esc(data['basis_date'])}</p></div>
      <div class="cover-brand">{esc(brand_name)}</div>
    </section>""")

    first, rest = data["sections"][0], data["sections"][1:]
    pages.append(render_section(first, data, 2, total))

    metric_html = "".join(
        f'<article class="metric"><span>{esc(item.get("label", ""))}</span><strong>{esc(item.get("value", ""))}</strong><small>{esc(item.get("note", ""))}</small></article>'
        for item in data["metrics"]
    )
    pages.append(f"""
    <section class="sheet page magazine overview-page">
      {magazine_badge(data)}<p class="part">DECISION OVERVIEW · {esc(mode_label)}</p><h1>{esc(overview['title'])}</h1>
      <div class="metric-grid">{metric_html}</div>
      <div class="overview-column">{paragraphs(overview.get('paragraphs', []))}</div>
      <div class="investment-lens"><b>한눈에 설명</b><span>{esc(overview['takeaway'])}</span></div>
      {evidence_note(overview, data)}
      <div class="basis-box"><b>분석 범위</b><span>{esc(target['name'])} · {esc(target['descriptor'])}</span><span>체결거래와 공개 호가를 분리해 해석 · 교육용 재구성</span></div>
      {page_footer(brand_name, 3, total)}
    </section>""")

    for page, section in enumerate(rest, start=4):
        pages.append(render_section(section, data, page, total))

    checklist_page = total - 1
    checks = "".join(f'<article class="check-item"><i>{i:02d}</i><div><b>{esc(item.get("title", ""))}</b><span>{esc(item.get("body", ""))}</span></div></article>' for i, item in enumerate(data["checklist"], 1))
    pages.append(f"""
    <section class="sheet page magazine checklist-page">{magazine_badge(data)}<p class="part">FIELD & CONTRACT CHECK</p>
      <h1>투자 판단은 현장에서<br>마지막으로 완성됩니다</h1>
      <p class="lead">데이터가 가격의 범위를 보여준다면, 계약 전 확인은 그 가격을 지불할 이유가 실제로 존재하는지 검증하는 과정입니다.</p>
      <div class="check-list">{checks}</div>
      <div class="notice">확인되지 않은 권리·대출·세금·현장 조건은 단정하지 않습니다. 계약서, 등기·공부, 금융기관, 현장 확인으로 각각 보완합니다.</div>
      {page_footer(brand_name, checklist_page, total)}
    </section>""")

    summary = data["summary"]
    cards = "".join(f'<article class="action"><b>{esc(item.get("title", ""))}</b><span>{esc(item.get("body", ""))}</span></article>' for item in summary["cards"])
    pages.append(f"""
    <section class="sheet closing magazine-closing">{magazine_badge(data)}<p class="part">FINAL NOTE · {esc(customer['role'])}</p>
      <h1>이번 분석을 정리하면<br>좋은 투자는 질문이<br>먼저입니다</h1>
      <div class="closing-summary">{paragraphs(summary.get('paragraphs', []))}</div><div class="actions">{cards}</div>
      <div class="closing-source">기준일 {esc(data['basis_date'])} · 교육용 재구성 시안</div>
      <div class="closing-brand">{esc(brand_name)}</div><div class="closing-disclaimer">{esc(data['disclaimer'])}</div>
    </section>""")

    audit = data.get("_evidence_audit", {})
    fingerprint = str(audit.get("evidence_fingerprint", ""))
    release_status = str(audit.get("derived_release_status", data.get("release_status", "HOLD")))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="evidence-audit-sha256" content="{esc(fingerprint)}"><meta name="derived-release-status" content="{esc(release_status)}">
    <title>{esc(target['name'])} 투자상담 매거진</title><style>
    :root{{--blue:{color};--navy:#122e72;--ink:#191b20;--muted:#6d7480;--line:#d9dee7;--paper:#fff;--soft:#f3f6fb;--orange:#ed6a48;--green:#167557}}
    *{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:#dfe4ec;color:var(--ink)}}body{{font-family:"Pretendard","Noto Sans KR","Malgun Gothic",sans-serif}}
    @page{{size:A4;margin:0}}@media print{{html,body{{background:#fff}}.sheet{{margin:0!important;box-shadow:none!important}}}}
    .sheet{{position:relative;width:210mm;height:297mm;margin:8mm auto;overflow:hidden;background:var(--paper);box-shadow:0 4mm 14mm rgba(20,38,70,.13);break-after:page;page-break-after:always}}.sheet:last-child{{break-after:auto}}
    .mag-demo{{position:absolute!important;right:12mm!important;top:9mm!important;z-index:50!important;width:auto!important;padding:2mm 4mm;border-radius:99px;background:#fff2c8;color:#704800;font-size:6.2pt;font-weight:900;box-shadow:0 1mm 3mm rgba(0,0,0,.12);white-space:nowrap}}
    .magazine-cover{{background:#071b4b;color:#fff}}.cover-photo{{position:absolute;inset:0}}.cover-photo img{{width:100%;height:100%;object-fit:cover;object-position:center 56%}}.cover-wash{{position:absolute;inset:0;background:linear-gradient(90deg,rgba(5,20,56,.94) 0%,rgba(5,20,56,.75) 44%,rgba(5,20,56,.08) 76%),linear-gradient(0deg,rgba(5,20,56,.55),transparent 46%)}}.cover-editorial{{position:absolute;left:16mm;top:25mm;width:112mm}}.issue{{font-size:7pt;font-weight:900;letter-spacing:.13em}}.magazine-cover h1{{margin:32mm 0 4mm;font-size:38pt;line-height:1.03;letter-spacing:-.07em;word-break:keep-all}}.cover-deck{{width:93mm;margin:0;font-family:"Nanum Myeongjo","Batang",serif;font-size:17pt;line-height:1.5;letter-spacing:-.035em;word-break:keep-all}}.cover-rule{{width:30mm;height:.6mm;margin:10mm 0 5mm;background:#fff}}.cover-meta{{font-size:7.5pt;line-height:1.75;color:rgba(255,255,255,.82)}}.cover-brand{{position:absolute;left:16mm;bottom:13mm;font-size:11pt;font-weight:900;letter-spacing:.06em}}
    .page{{padding:17mm 18mm 16mm}}.page::after{{content:"EZIWORK";position:absolute;right:-12mm;bottom:38mm;color:#17275a;opacity:.025;font-size:38pt;font-weight:900;transform:rotate(-90deg)}}.page>*{{position:relative;z-index:2}}.part{{margin:0 0 3mm;color:var(--navy);font-size:7pt;font-weight:900;letter-spacing:.12em}}.page h1{{margin:0 0 6mm;color:var(--blue);font-family:"Nanum Myeongjo","Batang",serif;font-size:28pt;line-height:1.22;letter-spacing:-.055em;word-break:keep-all}}.page h2{{margin:0 0 3mm;color:var(--navy);font-size:12pt;letter-spacing:-.035em}}.lead,.copy{{font-size:10.2pt;line-height:1.82;letter-spacing:-.025em;word-break:keep-all}}.lead{{margin:0 0 6mm;color:#343942}}.copy{{margin:0 0 3.5mm}}
    .footer{{position:absolute;left:18mm;right:18mm;bottom:7mm;display:flex;justify-content:space-between;color:#818792;font-size:6.2pt}}.caption{{margin:1.8mm 0 1mm;color:#777e88;font-size:6.4pt;line-height:1.4}}.source-links{{margin:0;color:#5e6d87;font-size:6.1pt;line-height:1.45}}.source-links b,.evidence-note b{{color:#263f73}}.source-links a{{color:#2856b5;text-decoration:none}}.evidence-note{{margin:1mm 0 4mm;color:#898f98;font-size:5.8pt;line-height:1.4}}
    .prologue{{padding:0;background:#fbfaf7}}.prologue-image{{position:absolute;left:0;top:0;width:88mm;height:297mm;overflow:hidden}}.prologue-image figure{{margin:0;width:100%;height:100%}}.prologue-image .evidence-image{{width:100%;height:100%;object-fit:cover;object-position:54% center}}.prologue-copy{{position:absolute;left:101mm;right:16mm;top:22mm;bottom:16mm}}.prologue h1{{font-size:27pt;color:var(--navy)}}.prologue .lead{{font-family:"Nanum Myeongjo","Batang",serif;font-size:13pt;font-weight:700;line-height:1.65}}.prologue .copy{{font-size:10pt;line-height:1.92}}.pull-quote{{margin:7mm 0;padding:5mm 0;border-top:.4mm solid var(--navy);border-bottom:.4mm solid var(--navy);color:var(--navy);font-family:"Nanum Myeongjo","Batang",serif;font-size:12pt;font-weight:700;line-height:1.7}}
    .metric-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin:2mm 0 9mm}}.metric{{min-height:33mm;padding:4.5mm;border-top:1.2mm solid var(--blue);background:#f7f9fd}}.metric span{{display:block;color:var(--muted);font-size:6.8pt}}.metric strong{{display:block;margin:2mm 0;color:var(--navy);font-size:16pt;letter-spacing:-.045em}}.metric small{{font-size:6pt;color:var(--muted)}}.overview-column{{columns:2;column-gap:8mm;margin:2mm 0 6mm;padding:6mm 0;border-top:.3mm solid var(--line);border-bottom:.3mm solid var(--line)}}.overview-column .copy{{font-size:10pt;line-height:1.9}}.investment-lens{{display:grid;grid-template-columns:28mm 1fr;gap:5mm;padding:5mm;background:var(--navy);color:#fff}}.investment-lens b{{font-size:8pt}}.investment-lens span{{font-family:"Nanum Myeongjo","Batang",serif;font-size:11.5pt;line-height:1.65}}.basis-box{{display:grid;gap:1.2mm;margin-top:6mm;padding:4mm;background:var(--soft);font-size:7pt;color:#626a76}}.basis-box b{{color:var(--navy)}}
    .diagram{{height:91mm;margin:0;padding:4mm;border-top:.4mm solid var(--line);border-bottom:.4mm solid var(--line)}}.diagram svg,.evidence-image{{display:block;width:100%;height:100%;object-fit:contain}}.story-grid{{display:grid;grid-template-columns:1.42fr .78fr;gap:8mm;margin-top:5mm}}.takeaway{{align-self:start;padding:5mm;border-top:1.2mm solid var(--orange);background:#f8f4f1;font-family:"Nanum Myeongjo","Batang",serif;font-size:10pt;font-weight:700;line-height:1.65}}.takeaway b{{display:block;margin-bottom:2mm;color:var(--orange);font-family:inherit;font-size:6.5pt;letter-spacing:.08em}}.takeaway.dark{{border-color:var(--navy);background:var(--navy);color:#fff}}.takeaway.dark b{{color:#b9d0ff}}
    .map-frame{{position:relative;height:124mm;margin:0;overflow:hidden;background:#dfe7ee;border:.3mm solid #ccd3dc}}.map-frame .evidence-image{{width:135%;height:135%;max-width:none;object-fit:cover;object-position:54% 50%;transform:translate(-12%,-13%)}}.map-pin{{position:absolute;left:52%;top:47%;padding:2mm 3mm;border-radius:99px;background:var(--blue);color:#fff;font-size:6pt;font-weight:900;box-shadow:0 1mm 3mm rgba(0,0,0,.25)}}.layout-map .lead{{margin-bottom:4mm}}.map-analysis{{margin-top:4mm;padding-top:4mm;border-top:1.1mm solid var(--orange)}}.map-analysis .copy{{max-width:150mm}}
    .matrix-diagram{{height:103mm}}.gridline{{stroke:#e4e7ed;stroke-width:1}}.axisline{{stroke:#aeb7c4;stroke-width:1.4}}.tick,.small-label{{fill:#6c7480;font-size:12px}}.label{{fill:#26303d;font-size:14px;font-weight:700}}.axis-title{{fill:#5c6470;font-size:13px}}.value{{fill:#173c88;font-size:13px;font-weight:900}}.dot{{fill:var(--blue)}}.target-dot{{fill:var(--orange);stroke:#fff;stroke-width:4}}.target-line{{stroke:var(--orange);stroke-width:2;stroke-dasharray:7 5}}.target-pill{{fill:var(--orange)}}.pill-text{{fill:#fff;font-size:11px;font-weight:900}}.ask-range{{stroke:var(--orange);stroke-width:12;stroke-linecap:round}}.legend{{fill:#57606c;font-size:12px}}.bar{{fill:var(--blue)}}.accent-bar{{fill:var(--orange)}}.bar-bg{{fill:#e8edf5}}.matrix-row{{fill:#f7f9fc;stroke:#d9dee7}}.status.ok{{fill:#dff3e9}}.status.warn{{fill:#fff0cf}}.status.hold{{fill:#ffe2df}}.status-text{{fill:#26323d;font-size:11px;font-weight:900}}
    .checklist-page h1{{font-size:30pt}}.check-list{{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-top:7mm}}.check-item{{display:flex;gap:4mm;min-height:30mm;padding:4mm;border-top:.5mm solid var(--navy);background:#f7f9fc}}.check-item i{{color:#aab4c5;font-family:serif;font-size:17pt;font-style:normal}}.check-item b{{display:block;margin-bottom:1.5mm;color:var(--navy);font-size:9pt}}.check-item span{{font-size:7.6pt;line-height:1.55;color:#505762}}.notice{{margin-top:5mm;padding:4mm;background:#fff1e8;color:#6d3b24;font-size:7.2pt;line-height:1.55}}
    .magazine-closing{{padding:20mm 18mm;background:var(--blue);color:#fff}}.magazine-closing .part{{color:#fff}}.magazine-closing h1{{margin:10mm 0 13mm;color:#fff;font-family:"Nanum Myeongjo","Batang",serif;font-size:34pt;line-height:1.18;letter-spacing:-.055em}}.closing-summary{{padding:7mm 0;border-top:.4mm solid rgba(255,255,255,.6);border-bottom:.4mm solid rgba(255,255,255,.6)}}.closing-summary .copy{{font-size:11pt;line-height:1.8}}.actions{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:9mm}}.action{{min-height:40mm;padding:5mm 4mm;background:#fff;color:#15305d}}.action b{{display:block;margin-bottom:2mm;font-size:8pt}}.action span{{font-size:7.4pt;line-height:1.5}}.closing-source{{margin-top:6mm;font-size:6.5pt;color:rgba(255,255,255,.78)}}.closing-brand{{position:absolute;left:18mm;bottom:15mm;font-size:11pt;font-weight:900}}.closing-disclaimer{{position:absolute;right:18mm;bottom:14mm;width:125mm;text-align:right;font-size:5.5pt;line-height:1.45;color:rgba(255,255,255,.75)}}
    </style></head><body>{''.join(pages)}</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an EZIWORK editorial real-estate investment brief.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()
    data = load_request(args.input)
    errors = validate_request(data)
    audit = data.get("_evidence_audit", {})
    if args.audit_output:
        write_audit(audit, args.audit_output)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    if audit.get("derived_release_status") == RELEASE_HOLD:
        print("ERROR: derived release status is HOLD; report was not created")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(data), encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
