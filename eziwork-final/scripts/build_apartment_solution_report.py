from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from build_report import (
    RELEASE_HOLD,
    esc,
    image_data_uri,
    load_request,
    validate_request,
    write_audit,
)


CUSTOMER_TYPES = {"BUY": "매수", "SELL": "매도"}
PAGE_COUNT = 10


def money(value: float) -> str:
    return f"{value:.2f}억"


def paragraphs(items: list[str]) -> str:
    return "".join(f'<p class="copy">{esc(item)}</p>' for item in items)


def demo_badge(data: dict[str, Any]) -> str:
    if data.get("evidence_mode") == "demo":
        return '<span class="demo-badge">교육용 예시 · 실제 시세가 아님</span>'
    return ""


def footer(data: dict[str, Any], page: int) -> str:
    brand = esc(data["brand"]["name"])
    return f'<footer><span>{brand} 아파트 가치·시세 분석</span><b>{page}</b></footer>'


def source_strip(data: dict[str, Any], source_ids: list[str]) -> str:
    source_map = {str(item.get("id")): item for item in data.get("sources", [])}
    labels: list[str] = []
    for source_id in source_ids:
        source = source_map.get(str(source_id), {})
        label = f'{esc(source.get("name", source_id))} · {esc(source.get("as_of", ""))}'
        url = str(source.get("url", ""))
        labels.append(f'<a href="{esc(url)}">{label}</a>' if url.startswith(("http://", "https://")) else label)
    return '<div class="source-strip"><b>자료</b> ' + " / ".join(labels) + "</div>"


def title_block(kicker: str, title: str, answer: str) -> str:
    return f"""
      <div class="main-column title-block">
        <p class="kicker">{esc(kicker)}</p>
        <h1>{esc(title)}</h1>
        <h2>{esc(answer)}</h2>
      </div>"""


def table_html(headers: list[str], rows: list[list[Any]], highlight: int | None = None) -> str:
    head = "".join(f"<th>{esc(item)}</th>" for item in headers)
    body: list[str] = []
    for index, row in enumerate(rows):
        class_name = ' class="highlight"' if index == highlight else ""
        body.append(f"<tr{class_name}>" + "".join(f"<td>{esc(item)}</td>" for item in row) + "</tr>")
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def building_svg() -> str:
    towers = [(70, 120, 95, 280), (185, 72, 105, 328), (315, 104, 92, 296), (430, 46, 118, 354), (575, 96, 96, 304)]
    shapes: list[str] = []
    for x, y, width, height in towers:
        shapes.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="3" fill="#d9e2ec" stroke="#75869a" stroke-width="2"/>')
        for window_y in range(y + 18, y + height - 10, 24):
            for window_x in range(x + 14, x + width - 8, 22):
                shapes.append(f'<rect x="{window_x}" y="{window_y}" width="9" height="12" fill="#f7c861" opacity=".72"/>')
    return f"""
    <svg viewBox="0 0 740 440" role="img" aria-label="교육용 아파트 단지 일러스트">
      <defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#183d78"/><stop offset=".66" stop-color="#8fb2cd"/><stop offset="1" stop-color="#f1caa6"/></linearGradient></defs>
      <rect width="740" height="440" fill="url(#sky)"/><circle cx="620" cy="76" r="34" fill="#fff3c8" opacity=".75"/>
      <path d="M0 388 Q170 350 330 385 T740 372 V440 H0Z" fill="#273b36"/>{''.join(shapes)}
      <path d="M0 401 H740" stroke="#eef2f5" stroke-width="6" opacity=".75"/>
      <text x="28" y="420" fill="#ffffff" font-size="15" font-weight="700">교육용 단지 일러스트 · 실제 건물 사진이 아님</text>
    </svg>"""


def map_svg(location: dict[str, Any]) -> str:
    labels = list(location.get("map_labels", ["역", "학교", "상권", "공원"]))[:4]
    while len(labels) < 4:
        labels.append("주요 시설")
    return f"""
    <svg viewBox="0 0 760 470" role="img" aria-label="교육용 위치 개념도">
      <rect width="760" height="470" fill="#eef1ea"/>
      <path d="M-40 120 C150 40 360 200 820 70" stroke="#83b8d5" stroke-width="42" fill="none" opacity=".85"/>
      <path d="M20 390 L700 45 M120 465 L755 170 M-20 260 L780 340" stroke="#ffffff" stroke-width="19" fill="none"/>
      <path d="M20 390 L700 45 M120 465 L755 170 M-20 260 L780 340" stroke="#c9c8bf" stroke-width="2" fill="none"/>
      <g fill="#d8dfd0" stroke="#b7c2b2"><rect x="65" y="174" width="120" height="76"/><rect x="210" y="270" width="150" height="90"/><rect x="520" y="220" width="150" height="90"/><rect x="570" y="370" width="110" height="58"/></g>
      <g font-family="sans-serif" font-size="17" font-weight="700" text-anchor="middle">
        <g transform="translate(382 238)"><circle r="45" fill="#ef5d4d"/><text y="6" fill="#fff">대상 단지</text></g>
        <g transform="translate(160 335)"><rect x="-54" y="-23" width="108" height="46" rx="8" fill="#3156a5"/><text y="6" fill="#fff">{esc(labels[0])}</text></g>
        <g transform="translate(610 150)"><rect x="-54" y="-23" width="108" height="46" rx="8" fill="#5a8d65"/><text y="6" fill="#fff">{esc(labels[1])}</text></g>
        <g transform="translate(110 210)"><rect x="-54" y="-23" width="108" height="46" rx="8" fill="#d78b3c"/><text y="6" fill="#fff">{esc(labels[2])}</text></g>
        <g transform="translate(620 340)"><rect x="-54" y="-23" width="108" height="46" rx="8" fill="#468ba3"/><text y="6" fill="#fff">{esc(labels[3])}</text></g>
      </g>
      <text x="20" y="448" fill="#5b655d" font-size="14">교육용 위치 개념도 · 실제 거리와 위치를 나타내지 않음</text>
    </svg>"""


def price_chart_svg(market: dict[str, Any]) -> str:
    transactions = market.get("transactions", [])
    listings = market.get("public_listings", [])
    values = [float(item["price"]) for item in transactions] + [float(item["price"]) for item in listings]
    low = math.floor((min(values) - 0.2) * 10) / 10
    high = math.ceil((max(values) + 0.2) * 10) / 10
    width, height = 760, 360
    left, right, top, bottom = 70, 25, 32, 56
    chart_w, chart_h = width - left - right, height - top - bottom

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * chart_h

    grid: list[str] = []
    for index in range(5):
        value = low + (high - low) * index / 4
        yy = y(value)
        grid.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#d9dde3"/>')
        grid.append(f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" fill="#6b737d" font-size="13">{value:.1f}억</text>')

    txn_points: list[str] = []
    txn_line: list[str] = []
    for index, item in enumerate(transactions):
        x = left + chart_w * index / max(1, len(transactions) - 1)
        yy = y(float(item["price"]))
        txn_points.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="5" fill="#f06442"/>')
        txn_line.append(f'{x:.1f},{yy:.1f}')
        if index in {0, len(transactions) - 1}:
            grid.append(f'<text x="{x:.1f}" y="{height-24}" text-anchor="middle" fill="#6b737d" font-size="13">{esc(item["date"])}</text>')

    listing_marks: list[str] = []
    for index, item in enumerate(listings):
        x = left + chart_w * (index + 0.5) / max(1, len(listings))
        yy = y(float(item["price"]))
        listing_marks.append(f'<rect x="{x-5:.1f}" y="{yy-5:.1f}" width="10" height="10" fill="#3156a5" opacity=".72"/>')

    return f"""
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="실거래와 공개 호가 분리 차트">
      <rect width="{width}" height="{height}" fill="#fff"/>{''.join(grid)}
      <polyline points="{' '.join(txn_line)}" fill="none" stroke="#f06442" stroke-width="4"/>{''.join(txn_points)}{''.join(listing_marks)}
      <g font-family="sans-serif" font-size="14"><circle cx="510" cy="18" r="5" fill="#f06442"/><text x="522" y="23" fill="#4b5158">체결 실거래</text><rect x="620" y="13" width="10" height="10" fill="#3156a5"/><text x="637" y="23" fill="#4b5158">현재 공개 호가</text></g>
    </svg>"""


def price_band_svg(price: dict[str, Any], perspective: dict[str, Any]) -> str:
    transaction = [float(item) for item in price["transaction_band"]]
    asking = [float(item) for item in price["asking_band"]]
    proposed = float(perspective["proposed_price"])
    low = min(transaction + asking + [proposed]) - 0.25
    high = max(transaction + asking + [proposed]) + 0.25
    x0, x1 = 70, 730

    def x(value: float) -> float:
        return x0 + (value - low) / (high - low) * (x1 - x0)

    ticks = []
    for index in range(6):
        value = low + (high - low) * index / 5
        xx = x(value)
        ticks.append(f'<line x1="{xx:.1f}" y1="208" x2="{xx:.1f}" y2="220" stroke="#7b8188"/><text x="{xx:.1f}" y="244" text-anchor="middle" fill="#626970" font-size="13">{value:.1f}</text>')
    return f"""
    <svg viewBox="0 0 800 270" role="img" aria-label="가격 구간과 검토 가격 위치">
      <rect width="800" height="270" fill="#fff"/><text x="70" y="35" fill="#20262c" font-size="16" font-weight="700">가격 위치 · 단위 억원</text>
      <text x="70" y="86" fill="#6a717a" font-size="14">체결 실거래 범위</text><line x1="{x(transaction[0]):.1f}" y1="112" x2="{x(transaction[1]):.1f}" y2="112" stroke="#f06442" stroke-width="18" stroke-linecap="round"/>
      <text x="70" y="148" fill="#6a717a" font-size="14">현재 공개 호가 범위</text><line x1="{x(asking[0]):.1f}" y1="174" x2="{x(asking[1]):.1f}" y2="174" stroke="#3156a5" stroke-width="18" stroke-linecap="round"/>
      <line x1="{x(proposed):.1f}" y1="60" x2="{x(proposed):.1f}" y2="206" stroke="#111" stroke-width="3" stroke-dasharray="7 5"/><rect x="{x(proposed)-63:.1f}" y="41" width="126" height="27" rx="5" fill="#111"/><text x="{x(proposed):.1f}" y="60" text-anchor="middle" fill="#fff" font-size="13" font-weight="700">{esc(perspective['proposed_label'])}</text>
      <line x1="{x0}" y1="214" x2="{x1}" y2="214" stroke="#7b8188"/>{''.join(ticks)}
    </svg>"""


def read_image_or_svg(path_value: str, base_dir: Path, fallback: str, alt: str) -> str:
    uri = image_data_uri(path_value, base_dir) if path_value else ""
    return f'<img src="{uri}" alt="{esc(alt)}">' if uri else fallback


def validate_solution(data: dict[str, Any], customer_type: str) -> list[str]:
    errors = validate_request(data)
    solution = data.get("solution", {})
    if customer_type not in CUSTOMER_TYPES:
        errors.append("customer_type must be BUY or SELL")
    for key in ("profile", "location", "living", "product", "market", "comparables", "price_analysis", "perspectives"):
        if not solution.get(key):
            errors.append(f"solution.{key} is required")
    if customer_type not in solution.get("perspectives", {}):
        errors.append(f"solution.perspectives.{customer_type} is required")
    source_ids = {str(item.get("id")) for item in data.get("sources", [])}
    if data.get("evidence_mode") == "actual":
        for key in ("profile", "location", "living", "product", "market", "comparables", "price_analysis"):
            ids = solution.get(key, {}).get("source_ids", [])
            if not ids:
                errors.append(f"solution.{key}.source_ids is required in actual mode")
            for source_id in ids:
                if source_id not in source_ids:
                    errors.append(f"solution.{key} references unknown source id: {source_id}")
    return errors


def render_report(data: dict[str, Any], customer_type: str) -> str:
    solution = data["solution"]
    profile = solution["profile"]
    location = solution["location"]
    living = solution["living"]
    product = solution["product"]
    market = solution["market"]
    comparables = solution["comparables"]
    price = solution["price_analysis"]
    perspective = solution["perspectives"][customer_type]
    target = data["target"]
    base_dir = Path(data["_base_dir"])
    badge = demo_badge(data)
    hero = read_image_or_svg(str(target.get("image_path", "")), base_dir, building_svg(), f"{target['name']} 단지 이미지")
    map_visual = read_image_or_svg(str(target.get("map_image_path", "")), base_dir, map_svg(location), f"{target['name']} 위치 지도")

    facts = "".join(f'<tr><th>{esc(item["label"])}</th><td>{esc(item["value"])}</td></tr>' for item in profile["facts"])
    key_points = "".join(f'<li><i>✓</i>{esc(item)}</li>' for item in profile["key_points"])
    commute_rows = [[item["destination"], item["transit"], item["car"]] for item in location["commute"]]
    school_rows = [[item["label"], item["value"], item["note"]] for item in living["education_rows"]]
    product_rows = [[item["type"], item["exclusive"], item["layout"], item["households"]] for item in product["unit_mix"]]
    transaction_rows = [[item["date"], money(float(item["price"])), item["floor"], item["note"]] for item in market["transactions"]]
    listing_rows = [[item["label"], money(float(item["price"])), item["condition"], item["checked_at"]] for item in market["public_listings"]]
    comparable_rows = [[item["name"], item["year"], item["households"], item["area"], money(float(item["reference_price"])), item["reading"]] for item in comparables["rows"]]
    decision_rows = [[item["step"], item["criterion"], item["action"]] for item in perspective["decision_rows"]]
    action_cards = "".join(f'<article><b>{esc(item["title"])}</b><span>{esc(item["body"])}</span></article>' for item in perspective["summary_cards"])

    pages: list[str] = []
    pages.append(f"""
    <section class="sheet cover">{badge}<p class="tiny-brand">아파트 솔루션 · {esc(CUSTOMER_TYPES[customer_type])} 관점</p>
      <div class="cover-rule"></div><div class="cover-title"><h1>[{esc(profile['district'])}] {esc(target['name'])}</h1><p>{esc(profile['subtitle'])}</p></div><div class="cover-rule lower"></div>
      <div class="cover-grid"><table class="fact-table"><caption>단지정보</caption><tbody>{facts}</tbody></table><figure class="hero">{hero}</figure></div>
      <ul class="key-points">{key_points}</ul><div class="cover-copy">{paragraphs(profile['intro_paragraphs'])}</div>
      {source_strip(data, profile['source_ids'])}{footer(data, 1)}
    </section>""")

    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[입지 가치 - 교통]', location['title'], location['answer'])}
      <div class="main-column narrative">{paragraphs(location['paragraphs'])}</div>
      <div class="wide-grid evidence-grid"><div><div class="bar-title">[표] 주요 업무·생활권 소요 시간</div>{table_html(['목적지','대중교통','자동차'], commute_rows)}</div><div><div class="bar-title">[그림] 대상 단지 인근 교통 환경</div><figure class="map">{map_visual}</figure></div></div>
      {source_strip(data, location['source_ids'])}{footer(data, 2)}
    </section>""")

    amenity_cards = "".join(f'<article><b>{esc(item["title"])}</b><span>{esc(item["body"])}</span></article>' for item in living["amenities"])
    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[생활 가치 - 교육·편의]', living['title'], living['answer'])}
      <div class="main-column narrative compact">{paragraphs(living['paragraphs'])}</div>
      <div class="wide-section"><div class="bar-title">[표] 교육·생활 조건 요약</div>{table_html(['구분','확인값','해석'], school_rows)}<div class="amenity-grid">{amenity_cards}</div></div>
      {source_strip(data, living['source_ids'])}{footer(data, 3)}
    </section>""")

    highlight_cards = "".join(f'<article><b>{esc(item["title"])}</b><span>{esc(item["body"])}</span></article>' for item in product["highlights"])
    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[상품 가치 - 단지·평형]', product['title'], product['answer'])}
      <div class="main-column narrative compact">{paragraphs(product['paragraphs'])}</div><div class="wide-section"><div class="highlight-grid">{highlight_cards}</div><div class="bar-title">[표] 주요 평형과 세대 구성</div>{table_html(['타입','전용면적','구조','세대수'], product_rows, product.get('highlight_row'))}</div>
      {source_strip(data, product['source_ids'])}{footer(data, 4)}
    </section>""")

    market_metrics = "".join(f'<article><b>{esc(item["value"])}</b><span>{esc(item["label"])}</span></article>' for item in market["metrics"])
    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[시장 흐름 - 거래·호가]', market['title'], market['answer'])}
      <div class="main-column narrative compact">{paragraphs(market['paragraphs'])}</div><div class="wide-section"><div class="bar-title">[그림] 실거래와 현재 공개 호가의 위치</div><figure class="chart">{price_chart_svg(market)}</figure><div class="metric-strip">{market_metrics}</div></div>
      {source_strip(data, market['source_ids'])}{footer(data, 5)}
    </section>""")

    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[가격 근거 - 자료 분리]', '체결 거래와 현재 매물을 따로 확인합니다', '같은 가격처럼 보여도 자료의 성격은 서로 다릅니다')}
      <div class="wide-section early"><div class="bar-title">[표] 최근 체결 실거래</div>{table_html(['계약일','거래가','층','비고'], transaction_rows)}<p class="lane-note">체결된 거래 · 취소·해제·신고 지연 처리 후 사용</p>
      <div class="bar-title spaced">[표] 현재 공개 매물 표본</div>{table_html(['구분','호가','조건','확인시각'], listing_rows)}<p class="lane-note">현재 공개 호가 · 중복 매물 여부와 실제 거래 가능 여부는 별도 확인</p></div>
      {source_strip(data, market['source_ids'])}{footer(data, 6)}
    </section>""")

    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[비교 분석 - 인근 단지]', comparables['title'], comparables['answer'])}
      <div class="main-column narrative compact">{paragraphs(comparables['paragraphs'])}</div><div class="wide-section"><div class="bar-title">[표] 인근 비교단지 요약</div>{table_html(['단지','준공','세대수','면적','기준가격','해석'], comparable_rows, comparables.get('highlight_row'))}<p class="lane-note">비교 기준: 동일 거래유형·유사 면적·완결기간. 상품 차이는 별도 설명합니다.</p></div>
      {source_strip(data, comparables['source_ids'])}{footer(data, 7)}
    </section>""")

    method_rows = [[item["label"], item["value"], item["basis"]] for item in price["method_rows"]]
    pages.append(f"""
    <section class="sheet page">{badge}{title_block('[가격 판단 - 근거 구간]', price['title'], price['answer'])}
      <div class="main-column narrative compact">{paragraphs(price['paragraphs'])}</div><div class="wide-section"><div class="bar-title">[그림] 실거래·호가·검토가격 위치</div><figure class="price-band">{price_band_svg(price, perspective)}</figure><div class="bar-title">[표] 판단 근거와 적용 방식</div>{table_html(['판단요소','확인값','적용'], method_rows)}</div>
      {source_strip(data, price['source_ids'])}{footer(data, 8)}
    </section>""")

    pages.append(f"""
    <section class="sheet page decision-page {customer_type.lower()}">{badge}{title_block(f'[{CUSTOMER_TYPES[customer_type]} 판단 - 실행 기준]', perspective['title'], perspective['answer'])}
      <div class="main-column narrative compact">{paragraphs(perspective['paragraphs'])}</div><div class="wide-section"><div class="bar-title">[표] {esc(CUSTOMER_TYPES[customer_type])} 의사결정 기준</div>{table_html(['단계','판단 기준','다음 행동'], decision_rows)}<div class="decision-quote"><b>한눈에 설명</b><span>{esc(perspective['takeaway'])}</span></div></div>
      {source_strip(data, perspective['source_ids'])}{footer(data, 9)}
    </section>""")

    pages.append(f"""
    <section class="sheet final-page">{badge}<p class="tiny-brand">FINAL BRIEF · {esc(CUSTOMER_TYPES[customer_type])} 관점</p><h1>이번 분석을<br>정리하면</h1>
      <div class="final-summary">{paragraphs(perspective['final_paragraphs'])}</div><div class="final-cards">{action_cards}</div>
      <div class="final-check"><b>계약·상담 전 마지막 확인</b><span>{esc(perspective['final_check'])}</span></div>
      <div class="final-meta">기준일 {esc(data['basis_date'])} · {esc(data['disclaimer'])}</div><div class="final-brand">{esc(data['brand']['name'])}</div>
    </section>""")

    audit = data.get("_evidence_audit", {})
    fingerprint = esc(audit.get("evidence_fingerprint", ""))
    release_status = esc(audit.get("derived_release_status", "HOLD"))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="evidence-audit-sha256" content="{fingerprint}"><meta name="derived-release-status" content="{release_status}">
    <title>{esc(target['name'])} {esc(CUSTOMER_TYPES[customer_type])} 아파트 솔루션</title><style>
    :root{{--blue:#2b66d6;--navy:#0c2e69;--ink:#15191e;--muted:#69717b;--line:#111;--soft:#ededed;--pale:#e8eef7;--coral:#f06442}}
    *{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:#d8d9da;color:var(--ink)}}body{{font-family:"Noto Sans KR","Pretendard","Malgun Gothic",sans-serif}}
    @page{{size:A4;margin:0}}@media print{{html,body{{background:#fff}}.sheet{{margin:0!important;box-shadow:none!important}}}}
    .sheet{{position:relative;width:210mm;height:297mm;margin:7mm auto;overflow:hidden;background:#fff;box-shadow:0 3mm 12mm rgba(0,0,0,.13);break-after:page;page-break-after:always}}.sheet:last-child{{break-after:auto}}
    .demo-badge{{position:absolute;right:11mm;top:7mm;z-index:20;padding:1.5mm 3mm;border:1px solid #d3a839;border-radius:99px;background:#fff5cf;color:#704f00;font-size:6.2pt;font-weight:800}}
    .tiny-brand{{position:absolute;left:15mm;top:11mm;margin:0;color:#4f68db;font-size:6.3pt;font-weight:800;letter-spacing:.02em}}footer{{position:absolute;left:68mm;right:15mm;bottom:8mm;display:flex;justify-content:space-between;color:#8b8f94;font-size:6.2pt}}footer b{{font-size:9pt;font-weight:500}}
    .cover{{padding:0 15mm}}.cover-rule{{position:absolute;left:15mm;right:15mm;top:24mm;height:.5mm;background:#111}}.cover-rule.lower{{top:53mm}}.cover-title{{position:absolute;left:15mm;right:15mm;top:29mm;text-align:center}}.cover-title h1{{margin:0;color:var(--navy);font-size:20pt;letter-spacing:-.05em}}.cover-title p{{margin:2mm 0 0;color:var(--blue);font-size:10pt;font-weight:700}}.cover-grid{{position:absolute;left:15mm;right:15mm;top:59mm;display:grid;grid-template-columns:54mm 1fr;gap:6mm}}.fact-table{{font-size:7.8pt}}.fact-table caption{{padding-bottom:3mm;text-align:left;font-size:9pt;font-weight:800}}.fact-table th,.fact-table td{{padding:2mm 1mm;border-bottom:.35mm solid #111;text-align:left;vertical-align:top}}.fact-table th{{width:19mm}}.hero{{height:91mm;margin:0;overflow:hidden;background:#d8e1e9}}.hero svg,.hero img{{width:100%;height:100%;object-fit:cover}}.key-points{{position:absolute;left:74mm;right:15mm;top:156mm;margin:0;padding:4mm 2mm;border-top:.45mm solid #111;border-bottom:.45mm solid #111;list-style:none}}.key-points li{{margin:1mm 0;font-size:8.4pt;font-weight:700}}.key-points i{{display:inline-grid;width:4mm;height:4mm;margin-right:2mm;place-items:center;background:#111;color:#fff;font-size:7pt;font-style:normal}}.cover-copy{{position:absolute;left:74mm;right:15mm;top:184mm}}.copy{{margin:0 0 4mm;font-size:8.8pt;line-height:1.7;letter-spacing:-.02em;word-break:keep-all}}.cover .source-strip{{left:74mm}}
    .page::before{{content:"";position:absolute;left:68mm;right:15mm;top:25mm;border-top:.45mm solid #111}}.main-column{{margin-left:68mm;margin-right:15mm}}.title-block{{padding-top:36mm}}.kicker{{margin:0 0 3mm;color:var(--blue);font-size:12.5pt;font-weight:800}}.title-block h1{{margin:0 0 4mm;font-size:10.8pt;line-height:1.45;letter-spacing:-.025em}}.title-block h2{{margin:0;color:#111;font-size:9pt;line-height:1.55;font-weight:700}}.narrative{{margin-top:10mm}}.narrative.compact{{margin-top:7mm}}.narrative .copy{{font-size:8.5pt;line-height:1.73}}.wide-grid,.wide-section{{position:absolute;left:15mm;right:15mm}}.evidence-grid{{bottom:35mm;display:grid;grid-template-columns:52mm 1fr;gap:5mm}}.wide-section{{top:135mm}}.wide-section.early{{top:70mm}}.bar-title{{padding:2.4mm 2mm;border-bottom:.55mm solid #111;background:#dedede;font-size:7.7pt;font-weight:800}}table{{width:100%;border-collapse:collapse;font-size:7.1pt}}th,td{{padding:2.2mm 1.8mm;border-right:.25mm solid #222;border-bottom:.25mm solid #c9c9c9;text-align:center;vertical-align:middle}}th:last-child,td:last-child{{border-right:0}}thead th{{background:#f4f4f4;font-weight:800}}tbody tr:last-child td{{border-bottom:.4mm solid #111}}tr.highlight td{{background:#dfe8f5;font-weight:800}}.map{{height:76mm;margin:0;border-bottom:.45mm solid #111;overflow:hidden}}.map svg,.map img{{width:100%;height:100%;object-fit:cover}}.source-strip{{position:absolute;left:15mm;right:15mm;bottom:18mm;padding-top:2mm;border-top:.4mm solid #111;color:#666;font-size:6pt}}.source-strip b{{color:#222}}.source-strip a{{color:#455f9d;text-decoration:none}}
    .amenity-grid,.highlight-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:6mm}}.amenity-grid article,.highlight-grid article{{min-height:32mm;padding:4mm;border-top:1mm solid var(--blue);background:#f5f6f7}}.amenity-grid b,.highlight-grid b{{display:block;margin-bottom:2mm;color:var(--navy);font-size:8pt}}.amenity-grid span,.highlight-grid span{{font-size:7pt;line-height:1.55}}.highlight-grid{{margin:0 0 6mm}}.chart{{height:86mm;margin:0;border-bottom:.45mm solid #111}}.chart svg{{width:100%;height:100%}}.metric-strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:4mm}}.metric-strip article{{padding:3mm;border-left:1mm solid var(--blue);background:#f2f4f7}}.metric-strip b{{display:block;color:var(--navy);font-size:12pt}}.metric-strip span{{font-size:6.8pt}}.lane-note{{margin:2mm 0;color:#6b7179;font-size:6.2pt}}.spaced{{margin-top:7mm}}.price-band{{height:66mm;margin:0}}.price-band svg{{width:100%;height:100%}}.decision-quote{{display:grid;grid-template-columns:28mm 1fr;gap:5mm;margin-top:7mm;padding:5mm;background:var(--navy);color:#fff}}.decision-quote b{{font-size:8pt}}.decision-quote span{{font-size:10pt;line-height:1.6;font-weight:700}}
    .final-page{{padding:23mm 15mm;background:#fff}}.final-page::before{{content:"";position:absolute;left:15mm;right:15mm;top:25mm;border-top:.5mm solid #111}}.final-page h1{{margin:36mm 0 12mm 53mm;color:var(--navy);font-size:31pt;line-height:1.2;letter-spacing:-.06em}}.final-summary{{margin-left:53mm;padding:7mm 0;border-top:.45mm solid #111;border-bottom:.45mm solid #111}}.final-summary .copy{{font-size:9.5pt}}.final-cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm;margin:12mm 0 0 53mm}}.final-cards article{{min-height:38mm;padding:5mm 4mm;border-top:1mm solid var(--blue);background:#f1f3f6}}.final-cards b{{display:block;margin-bottom:3mm;color:var(--navy);font-size:8pt}}.final-cards span{{font-size:7.2pt;line-height:1.55}}.final-check{{margin:8mm 0 0 53mm;padding:5mm;background:#e7edf7}}.final-check b{{display:block;margin-bottom:2mm;color:var(--navy);font-size:8pt}}.final-check span{{font-size:7.4pt;line-height:1.5}}.final-meta{{position:absolute;left:68mm;right:15mm;bottom:27mm;color:#70767e;font-size:5.8pt;line-height:1.5}}.final-brand{{position:absolute;left:15mm;bottom:13mm;color:var(--navy);font-size:11pt;font-weight:900;letter-spacing:.08em}}
    </style></head><body>{''.join(pages)}</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the reference-backed BUY/SELL apartment solution report.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--customer-type", required=True, choices=sorted(CUSTOMER_TYPES))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()

    data = load_request(args.input)
    errors = validate_solution(data, args.customer_type)
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
    args.output.write_text(render_report(data, args.customer_type), encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
