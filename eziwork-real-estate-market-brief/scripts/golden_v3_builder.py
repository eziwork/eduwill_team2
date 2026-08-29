from __future__ import annotations

import html
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ENGINE_ID = "EZIWORK_GOLDEN_V3"
ENGINE_VERSION = "3.1.0"
PAGE_COUNT = 9


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_krw(value: Any) -> str:
    amount = number(value)
    if amount is None:
        return "자료 보완"
    if abs(amount) >= 100_000_000:
        text = f"{amount / 100_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}억원"
    if abs(amount) >= 10_000:
        return f"{amount / 10_000:,.0f}만원"
    return f"{amount:,.0f}원"


def page_footer(brand: str, page: int) -> str:
    return f'<div class="brand">{esc(brand)}</div><div class="page-no">{page:02d} / {PAGE_COUNT:02d}</div>'


def metric_cards(metrics: list[dict[str, Any]]) -> str:
    cards = []
    for index, item in enumerate(metrics[:3]):
        value = str(item.get("value") or "자료 보완")
        muted = value in {"확인 불가", "자료 보완"}
        cards.append(
            f'<div class="card metric-card {"muted-card" if muted else ""}">'
            f'<div class="metric {"orange" if index == 2 and not muted else ""}">{esc("자료 보완" if muted else value)}</div>'
            f'<div class="metric-label">{esc(item.get("label", "확인 항목"))} · {esc(item.get("note", ""))}</div></div>'
        )
    while len(cards) < 3:
        cards.append('<div class="card metric-card muted-card"><div class="metric">자료 보완</div><div class="metric-label">확인 자료가 추가되면 자동 반영</div></div>')
    return "".join(cards)


def _role_copy(role: str, target: str) -> dict[str, str]:
    if "매도" in role or "소유" in role:
        return {
            "cover": "현재 시장에서 매물의 장점과 상담 포인트를 한눈에 정리합니다.",
            "fit": f"{target}의 가격 근거와 현장 가치를 함께 정리하면 매도 상담의 설득력을 높일 수 있습니다.",
            "headline": "시장 근거와 현장 장점을 함께 보여주면, 매물의 경쟁력을 더 선명하게 설명할 수 있습니다.",
            "cta": "현장 점검 → 매물 강점 정리 → 매도 조건 상담",
        }
    if "임대" in role:
        return {
            "cover": "현재 임대시장과 물건의 활용 가치를 함께 살펴봅니다.",
            "fit": f"{target}의 조건과 현장 장점을 확인하면 고객에게 맞는 임대 조건을 구체화할 수 있습니다.",
            "headline": "시장 조건과 현장 가치를 확인해, 고객에게 맞는 임대 조건을 상담해 보세요.",
            "cta": "현장 확인 → 임대 가치 정리 → 조건 상담",
        }
    if "임차" in role or "운영" in role:
        return {
            "cover": "예산과 이용 목적에 맞는 선택인지 시장 근거와 현장 조건으로 확인합니다.",
            "fit": f"{target}의 시장 위치와 실제 이용 가치를 함께 비교하면 선택 기준이 구체화됩니다.",
            "headline": "예산과 이용 목적에 맞는지 현장에서 확인하고, 고객에게 적합한 조건을 상담해 보세요.",
            "cta": "현장 방문 → 이용 가치 확인 → 조건 상담",
        }
    return {
        "cover": "가격 근거와 생활 가치, 향후 시장성을 함께 살펴봅니다.",
        "fit": f"{target}의 시장 위치와 현장 가치를 함께 확인하면 예산 안에서의 경쟁력을 구체적으로 판단할 수 있습니다.",
        "headline": "예산 안에서 비교 가능한 선택인지, 현장에서 세대의 실제 가치를 확인해 보세요.",
        "cta": "현장 방문 → 세대 가치 확인 → 계약 조건 상담",
    }


def _source_list(data: dict[str, Any], limit: int = 6) -> str:
    rows = []
    for source in data.get("sources", [])[:limit]:
        source_id = esc(source.get("id", "SRC"))
        name = esc(source.get("name", "근거자료"))
        as_of = esc(source.get("as_of", data.get("basis_date", "")))
        url = str(source.get("url", ""))
        link = f'<a href="{esc(url)}">원문</a>' if url.startswith(("http://", "https://")) else '<span>내부 확인</span>'
        rows.append(f'<li><b>{source_id}</b><div><strong>{name}</strong><small>기준 {as_of}</small></div>{link}</li>')
    return "".join(rows)


def _transaction_value(row: dict[str, Any], mode: str) -> float | None:
    if mode == "monthly_rent":
        return number(row.get("monthly_rent_krw"))
    if mode == "jeonse":
        return number(row.get("deposit_krw") or row.get("price_krw"))
    return number(row.get("price_krw"))


def _transaction_table(rows: list[dict[str, Any]], mode: str) -> str:
    items = []
    for row in sorted(rows, key=lambda item: str(item.get("contract_date", "")), reverse=True)[:8]:
        floor = number(row.get("floor"))
        floor_text = f"{int(floor)}층" if floor is not None else "층 확인"
        building = str(row.get("building") or "대상 범위")
        items.append(
            f'<tr><td>{esc(row.get("contract_date") or "날짜 확인")}</td><td>{esc(building)}</td>'
            f'<td>{esc(floor_text)}</td><td><b>{esc(fmt_krw(_transaction_value(row, mode)))}</b></td></tr>'
        )
    if not items:
        return '<tr><td colspan="4" class="table-empty">공식 거래자료가 추가되면 동일한 형식으로 자동 반영됩니다.</td></tr>'
    return "".join(items)


def _activity_svg(rows: list[dict[str, Any]], mode: str) -> str:
    by_month: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        date = str(row.get("contract_date") or "")
        value = _transaction_value(row, mode)
        if len(date) >= 7 and value is not None:
            by_month[date[:7]].append(value)
    months = sorted(by_month)[-12:]
    if not months:
        return '<div class="visual-empty"><b>시장 활동 데이터 연결 대기</b><span>공식 거래자료가 확보되면 월별 거래량과 가격 방향을 이 영역에 표시합니다.</span></div>'
    counts = [len(by_month[key]) for key in months]
    medians = [statistics.median(by_month[key]) for key in months]
    width, height, left, right, top, bottom = 720, 290, 54, 34, 28, 48
    step = (width - left - right) / max(1, len(months))
    max_count = max(counts) or 1
    min_price, max_price = min(medians), max(medians)
    if min_price == max_price:
        min_price *= .95
        max_price *= 1.05
    y_count = lambda value: top + (max_count - value) / max_count * (height - top - bottom)
    y_price = lambda value: top + (max_price - value) / (max_price - min_price) * (height - top - bottom)
    bars = []
    points = []
    labels = []
    for index, key in enumerate(months):
        x = left + index * step + step * .18
        bar_width = max(8, step * .64)
        y = y_count(counts[index])
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{height-bottom-y:.1f}" rx="3" fill="#75ace7"/>')
        px = left + index * step + step / 2
        py = y_price(medians[index])
        points.append((px, py))
        labels.append(f'<text x="{px:.1f}" y="{height-18}" text-anchor="middle" class="svg-label">{esc(key[2:])}</text>')
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#f37021" stroke="#fff" stroke-width="2"/>' for x, y in points)
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="월별 거래량과 중앙가격">'
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#cbd8e5"/>'
        f'{"".join(bars)}<polyline points="{polyline}" fill="none" stroke="#f37021" stroke-width="3"/>{dots}{"".join(labels)}'
        f'<rect x="{left}" y="8" width="11" height="11" rx="2" fill="#75ace7"/><text x="{left+17}" y="18" class="svg-legend">거래건수</text>'
        f'<line x1="{left+98}" y1="14" x2="{left+118}" y2="14" stroke="#f37021" stroke-width="3"/><text x="{left+126}" y="18" class="svg-legend">중앙가격</text></svg>'
    )


def _location_content(
    data: dict[str, Any],
    base_dir: Path,
    image_loader: Callable[[str, Path], str],
) -> str:
    target = data["target"]
    routes = []
    for route in target.get("walking_routes", []):
        minutes = number(route.get("minutes"))
        if minutes is not None and minutes <= 10:
            routes.append(route)
    map_uri = image_loader(str(target.get("map_image_path", "")), base_dir)
    cards = []
    if map_uri:
        cards.append(f'<div class="route-card route-map"><img src="{map_uri}" alt="{esc(target.get("name"))} 위치 지도"><div class="route-badge"><b>대상 위치</b><small>{esc(target.get("address", ""))}</small></div></div>')
    for route in routes[:4]:
        route_uri = image_loader(str(route.get("image_path", "")), base_dir)
        visual = f'<img src="{route_uri}" alt="{esc(route.get("destination", "도보 경로"))}">' if route_uri else '<div class="route-gradient"></div>'
        distance = str(route.get("distance") or route.get("distance_m") or "")
        cards.append(
            f'<div class="route-card">{visual}<div class="route-badge"><b>{esc(route.get("category", "편의시설"))} · {int(float(route["minutes"]))}분</b>'
            f'<small>{esc(route.get("destination", "확인된 목적지"))}{(" · " + esc(distance)) if distance else ""}</small></div></div>'
        )
    if cards:
        return f'<div class="route-grid count-{min(len(cards), 4)}">{"".join(cards)}</div>'
    return (
        '<div class="location-empty"><div class="location-pin">⌖</div>'
        f'<h3>{esc(target.get("name"))}</h3><p>{esc(target.get("address", "주소 확인 필요"))}</p>'
        '<span>검증된 도보 10분 이내 경로만 표시하는 기준을 적용했습니다. 경로 자료가 연결되면 확인된 시설만 이 페이지에 추가됩니다.</span></div>'
    )


def render_golden_v3(
    data: dict[str, Any],
    *,
    render_visual: Callable[[dict[str, Any], Path], str],
    image_loader: Callable[[str, Path], str],
    source_line_renderer: Callable[[dict[str, Any], dict[str, Any]], str],
    demo_badge_renderer: Callable[[dict[str, Any]], str],
) -> str:
    base_dir = Path(data["_base_dir"])
    target = data["target"]
    customer = data["customer"]
    brand = data["brand"]
    brand_name = str(brand.get("name") or "EZIWORK")
    target_name = str(target.get("name") or "대상 부동산")
    mode = str(data.get("mode") or "sale")
    mode_label = {"sale": "매매", "jeonse": "전세", "monthly_rent": "월세", "commercial_lease": "상가 임대", "land_lease": "토지 임대"}.get(mode, "부동산")
    role_copy = _role_copy(str(customer.get("role", "")), target_name)
    audit = data.get("_evidence_audit", {})
    release_status = str(audit.get("derived_release_status", data.get("release_status", "HOLD")))
    verification_id = str(audit.get("combined_release_fingerprint", ""))[:16]
    golden = data.get("golden_v3") if isinstance(data.get("golden_v3"), dict) else {}
    official_rows = [row for row in golden.get("official_transactions", []) if isinstance(row, dict)]
    listings = [row for row in golden.get("current_listings", []) if isinstance(row, dict)]
    sections = list(data.get("sections", []))
    official_section = sections[0] if sections else {"visual": {"type": "matrix", "rows": []}, "claim_ids": [], "source_ids": []}
    listing_section = sections[1] if len(sections) > 1 else official_section
    photo_uri = image_loader(str(target.get("image_path", "")), base_dir)
    cover_visual = f'<div class="cover-photo"><img src="{photo_uri}" alt="{esc(target_name)} 확인 이미지"></div>' if photo_uri else '<div class="cover-gradient" aria-hidden="true"></div>'
    official_visual = render_visual(official_section.get("visual", {}), base_dir)
    listing_visual = render_visual(listing_section.get("visual", {}), base_dir)
    location_html = _location_content(data, base_dir, image_loader)
    metrics = list(data.get("metrics", []))
    checks = list(data.get("checklist", []))
    holding = number(golden.get("holding_years"))
    horizon_text = f"{int(holding)}년 계획" if holding is not None else "고객 계획"
    price_context = golden.get("proposed_price_krw") or golden.get("budget_krw")
    price_text = fmt_krw(price_context) if price_context else "조건 상담"
    if mode == "monthly_rent" and len(metrics) >= 2:
        price_text = f"보증금 {metrics[0].get('value', '자료 보완')} · 월세 {metrics[1].get('value', '자료 보완')}"
    listing_prices = [number(row.get("price_krw")) for row in listings]
    listing_prices = [value for value in listing_prices if value is not None]
    official_values = [_transaction_value(row, mode) for row in official_rows]
    official_values = [value for value in official_values if value is not None]
    latest_value = _transaction_value(max(official_rows, key=lambda row: str(row.get("contract_date", ""))), mode) if official_rows else None
    source_note_official = source_line_renderer(official_section, data)
    source_note_listing = source_line_renderer(listing_section, data)
    badge = lambda: demo_badge_renderer(data)

    pages = []
    pages.append(f'''<section class="sheet page cover dark">{badge()}<div class="cover-main"><div class="eyebrow">{esc(brand_name)} · REAL ESTATE CUSTOMER BRIEF</div><h1 class="cover-title">{esc(target_name)}<br>{esc(mode_label)} 고객 상담 리포트</h1><p class="cover-sub">{esc(role_copy["cover"])}</p><div class="cover-facts"><span>{esc(target.get("descriptor", ""))}</span><span>{esc(price_text)}</span><span>{esc(horizon_text)}</span><span>기준일 {esc(data.get("basis_date", ""))}</span></div></div>{cover_visual}{page_footer(brand_name, 1)}</section>''')

    scope_items = [
        ("1", "대상과 고객 질문", f'{target_name} · {customer.get("role", "고객")} 관점'),
        ("2", "공식 거래 근거", f'유효 거래 {len(official_rows)}건 · 완료 거래만 분리'),
        ("3", "현재 선택지", f'확인한 공개매물 {len(listings)}건 · 호가 별도 표시' if listings else "표본 자료가 연결되면 호가를 별도 표시"),
        ("4", "가격 위치", f'{price_text} 조건을 실거래·호가와 비교'),
        ("5", "생활권과 현장 가치", "검증된 도보 10분 경로와 현장 체크"),
        ("6", "시장 활동과 다음 행동", "거래 방향을 상담 흐름으로 연결"),
    ]
    scope_html = "".join(f'<div class="analysis-item"><b>{num}</b><div><strong>{esc(title)}</strong><small>{esc(body)}</small></div></div>' for num, title, body in scope_items)
    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">PROLOGUE</div><h1 class="h1 question-title">{esc(customer.get("question", "어떤 선택이 좋을까요?"))}</h1><p class="prologue-copy">이 리포트는 공식 거래, 현재 공개매물, 대상의 위치와 현장 가치, 시장 활동을 분리해 비교합니다. 확인된 근거를 바탕으로 고객이 계속 관심을 갖고 현장에서 가치를 확인할 수 있도록 상담 포인트를 정리했습니다.</p><div class="analysis-list">{scope_html}</div><div class="decision-band"><div><span class="status">한눈에 설명 · 가치 확인</span><p>{esc(role_copy["fit"])}</p></div><strong>{esc(role_copy["cta"])}</strong></div>{page_footer(brand_name, 2)}</section>''')

    cards = metric_cards(metrics)
    visit_checks = checks[:3] or [
        {"title": "현장 가치", "body": "층·향·채광·전망과 내부 상태를 확인합니다."},
        {"title": "거래 조건", "body": "인도·잔금·관리·권리 조건을 상담합니다."},
        {"title": "시장 비교", "body": "동일 범위의 거래와 공개매물을 함께 비교합니다."},
    ]
    check_html = "".join(f'<div class="step"><span class="pill">VALUE {index}</span><b>{esc(item.get("title", "확인 항목"))}</b><p>{esc(item.get("body", ""))}</p></div>' for index, item in enumerate(visit_checks, 1))
    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">SUBJECT & VALUE FRAME</div><h2 class="h2">{esc(target_name)}의 가치를 무엇으로 확인할까요?</h2><div class="grid3">{cards}</div><div class="grid2 value-frame"><div class="card soft"><h3 class="h3">시장 비교 기준</h3><table class="table"><tbody><tr><td>검토 조건</td><td><b>{esc(price_text)}</b></td></tr><tr><td>최근 유효 거래</td><td><b>{esc(fmt_krw(latest_value))}</b></td></tr><tr><td>실거래 범위</td><td><b>{esc((fmt_krw(min(official_values)) + " ~ " + fmt_krw(max(official_values))) if official_values else "자료 보완")}</b></td></tr><tr><td>공개 호가 범위</td><td><b>{esc((fmt_krw(min(listing_prices)) + " ~ " + fmt_krw(max(listing_prices))) if listing_prices else "현장 상담 시 확인")}</b></td></tr></tbody></table></div><div class="card"><h3 class="h3">고객 관점의 핵심</h3><p class="lead-small">{esc(role_copy["fit"])}</p><div class="callout">확인된 숫자는 비교 기준으로 사용하고, 실제 경쟁력은 현장에서 확인되는 가치 요소와 함께 설명합니다.</div></div></div><h3 class="h3 value-heading">현장에서 확인할 세 가지 가치</h3><div class="ladder">{check_html}</div>{page_footer(brand_name, 3)}</section>''')

    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">LOCATION & WALKING ROUTES</div><h2 class="h2">위치와 생활권 — 검증된 도보 10분 경로</h2><div class="address-card"><b>{esc(target_name)}</b><span>{esc(target.get("address", "주소 확인 필요"))}</span></div>{location_html}<p class="note route-note">도보 경로는 제공자·기준일·출발지에 따라 달라질 수 있습니다. 10분을 초과하거나 검증되지 않은 시설은 고객용 화면에 표시하지 않습니다.</p>{page_footer(brand_name, 4)}</section>''')

    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">PRICE POSITION</div><h2 class="h2">검토 조건은 현재 거래 근거에서 어디에 있을까요?</h2><div class="grid3 compact-metrics">{cards}</div><div class="chart dominant-chart">{official_visual}</div><div class="grid2 evidence-copy"><div class="card"><h3 class="h3">가격을 읽는 기준</h3><p>{esc(official_section.get("body", "공식 거래와 고객 조건을 같은 비교범위에서 확인합니다."))}</p></div><div class="card orange"><h3 class="h3">상담 포인트</h3><p>{esc(role_copy["fit"])}</p></div></div>{source_note_official}{page_footer(brand_name, 5)}</section>''')

    table_rows = _transaction_table(official_rows, mode)
    range_copy = (f'{fmt_krw(min(official_values))}부터 {fmt_krw(max(official_values))}까지 실제 계약 사례가 확인됩니다.' if official_values else '공식 거래자료가 연결되면 날짜·동·층·가격을 동일한 형식으로 비교합니다.')
    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">OFFICIAL TRANSACTIONS</div><h2 class="h2">실제 계약 사례를 조건별로 확인합니다</h2><div class="grid2 transaction-head"><div class="card soft"><div class="metric">{len(official_rows)}건</div><div class="metric-label">선택 범위의 유효 거래</div></div><div class="card"><h3 class="h3">거래 범위 해석</h3><p>{esc(range_copy)}</p></div></div><div class="card transaction-card"><table class="table transaction-table"><thead><tr><th>계약일</th><th>동·구분</th><th>층</th><th>거래조건</th></tr></thead><tbody>{table_rows}</tbody></table></div><div class="callout navy">같은 면적과 비슷한 조건에서도 세대 상태와 계약 시점에 따라 차이가 생깁니다. 현장에서 대상 물건의 장점을 확인하면 가격 경쟁력을 더 구체적으로 설명할 수 있습니다.</div><div class="grid3 trade-insights"><div class="card"><span class="pill">COMPARE</span><h3 class="h3">같은 범위 비교</h3><p>동일 유형·면적·기간의 계약 사례를 기준으로 가격 차이를 설명합니다.</p></div><div class="card"><span class="pill">VALUE</span><h3 class="h3">현장 가치 확인</h3><p>층·향·채광·전망·수리 상태가 실제 경쟁력을 만드는지 확인합니다.</p></div><div class="card orange"><span class="pill">CONSULT</span><h3 class="h3">조건 상담</h3><p>잔금·인도·관리·권리 조건을 함께 정리해 고객 상담으로 연결합니다.</p></div></div>{source_note_official}{page_footer(brand_name, 6)}</section>''')

    activity = _activity_svg(official_rows, mode)
    active_months = len({str(row.get("contract_date", ""))[:7] for row in official_rows if len(str(row.get("contract_date", ""))) >= 7})
    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">MARKET ACTIVITY</div><h2 class="h2">거래 활동과 가격 방향을 함께 봅니다</h2><div class="grid3 compact-metrics"><div class="card metric-card"><div class="metric">{len(official_rows)}건</div><div class="metric-label">유효 거래</div></div><div class="card metric-card"><div class="metric">{active_months}개월</div><div class="metric-label">거래가 확인된 월</div></div><div class="card metric-card orange"><div class="metric orange">{esc(horizon_text)}</div><div class="metric-label">고객의 이용·보유 관점</div></div></div><div class="chart activity-chart">{activity}</div><div class="market-summary"><div class="macro"><h4>시장 참여</h4><p>거래건수는 고객이 현재 시장의 활동성을 이해하는 기준입니다.</p></div><div class="macro"><h4>가격 선택 폭</h4><p>중앙가격 방향과 개별 거래의 차이를 함께 보면 선택지가 더 선명해집니다.</p></div><div class="macro"><h4>현장 경쟁력</h4><p>층·향·상태·접근성은 같은 가격대 안에서 물건의 차별점을 만듭니다.</p></div><div class="macro"><h4>향후 상담</h4><p>시장 흐름을 단정하기보다 고객 계획과 매물 가치를 함께 상담합니다.</p></div></div>{source_note_official}{page_footer(brand_name, 7)}</section>''')

    listing_range = (f'{fmt_krw(min(listing_prices))} ~ {fmt_krw(max(listing_prices))}' if listing_prices else '현장 상담 시 확인')
    pages.append(f'''<section class="sheet page">{badge()}<div class="eyebrow">CURRENT COMPETITION</div><h2 class="h2">현재 공개매물에서 대상의 경쟁력을 확인합니다</h2><div class="grid3 compact-metrics"><div class="card metric-card"><div class="metric">{(str(len(listings)) + "건") if listings else "자료 보완"}</div><div class="metric-label">확인한 공개매물 표본</div></div><div class="card metric-card"><div class="metric range-metric">{esc(listing_range)}</div><div class="metric-label">공개 호가 범위</div></div><div class="card metric-card orange"><div class="metric orange">{esc(price_text)}</div><div class="metric-label">고객 검토 조건</div></div></div><div class="chart dominant-chart listing-chart">{listing_visual}</div><div class="grid2 evidence-copy"><div class="card"><h3 class="h3">현재 선택지</h3><p>{esc(listing_section.get("body", "공개매물은 조회시점의 선택지이며 실제 거래 가능 여부를 현장에서 확인합니다."))}</p></div><div class="card orange"><h3 class="h3">고객에게 보여줄 가치</h3><p>대상 물건의 위치·상태·관리·이용 장점을 비교하면 공개 호가 안에서의 경쟁력을 구체적으로 설명할 수 있습니다.</p></div></div><div class="competition-band"><b>공개 호가는 계약가격이 아닙니다.</b><span>대상 물건의 장점과 실제 거래 가능 조건을 현장에서 확인하면 현재 선택지 안에서의 경쟁력을 더 선명하게 설명할 수 있습니다.</span></div>{source_note_listing}{page_footer(brand_name, 8)}</section>''')

    final_checks = checks[:4]
    final_check_html = "".join(f'<li><div><b>{esc(item.get("title", "확인 항목"))}</b> · {esc(item.get("body", ""))}</div></li>' for item in final_checks)
    sources_html = _source_list(data)
    pages.append(f'''<section class="sheet page final-page dark">{badge()}<div class="eyebrow final-eyebrow">FINAL DECISION & NEXT ACTION</div><div class="final-decision">이번 분석을 정리하면,<br><em>{esc(role_copy["headline"])}</em></div><div class="grid2 final-grid"><div class="card darkcard"><h3 class="h3 light">시장 근거</h3><table class="table dark-table"><tbody><tr><td>검토 조건</td><td><b>{esc(price_text)}</b></td></tr><tr><td>유효 거래</td><td><b>{len(official_rows)}건</b></td></tr><tr><td>공개매물 표본</td><td><b>{(str(len(listings)) + "건") if listings else "자료 보완"}</b></td></tr><tr><td>계획</td><td><b>{esc(horizon_text)}</b></td></tr></tbody></table><p class="dark-note">금리·지역 시장 자료가 수집된 경우 같은 엔진의 시장 근거 영역에 날짜와 출처를 표시합니다.</p></div><div class="card"><h3 class="h3">핵심 판단</h3><p>{esc(role_copy["fit"])}</p><h3 class="h3 next-title">확인할 사항</h3><ul class="checklist">{final_check_html}</ul></div></div><div class="card orange final-action"><h3 class="h3">다음 행동</h3><p>확인된 시장 근거를 바탕으로 현장에서 물건의 실제 가치를 점검하고, 고객에게 맞는 조건을 상담합니다.</p><div class="callout orange-callout">{esc(role_copy["cta"])}</div></div><div class="source-block"><ul class="sources">{sources_html}</ul></div><div class="verification">엔진 {ENGINE_ID} {ENGINE_VERSION} · 기준일 {esc(data.get("basis_date", ""))} · {esc(release_status)} · 검증ID {esc(verification_id)}</div><p class="closing-disclaimer">{esc(data.get("disclaimer", ""))}</p>{page_footer(brand_name, 9)}</section>''')

    css = f'''
@page{{size:A4;margin:0}}*{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:#e9eef5;color:#132238;font-family:"Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}}body{{--watermark:"{esc(target_name)}"}}.sheet{{width:210mm;height:297mm;margin:0 auto 8mm;position:relative;overflow:hidden;page-break-after:always;background:#f8fbff;padding:15mm 15mm 14mm}}.sheet:last-child{{page-break-after:auto}}.page:before{{content:var(--watermark);position:absolute;left:12mm;top:126mm;font-size:18mm;font-weight:900;letter-spacing:-1.5mm;color:rgba(12,58,97,.035);transform:rotate(-24deg);white-space:nowrap;pointer-events:none}}.page>*{{position:relative;z-index:1}}.brand,.page-no{{position:absolute;bottom:7mm;font-size:8.5pt}}.brand{{left:15mm;color:#0a67ff;font-weight:900;letter-spacing:.12em}}.page-no{{right:15mm;color:#738399}}.eyebrow{{color:#0a67ff;font-size:9pt;font-weight:800;letter-spacing:.16em;text-transform:uppercase}}.h1{{font-size:28pt;line-height:1.18;letter-spacing:-.06em;margin:5mm 0 4mm;word-break:keep-all}}.h2{{font-size:20pt;line-height:1.22;letter-spacing:-.05em;margin:1.5mm 0 5mm;word-break:keep-all}}.h3{{font-size:12pt;margin:0 0 2.5mm;color:#0b2f55}}.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:5mm}}.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}}.card{{background:#fff;border:1px solid #dce7f1;border-radius:4mm;padding:4.2mm;box-shadow:0 2mm 8mm rgba(9,38,67,.05)}}.card.soft{{background:#edf6ff;border-color:#d5e9ff}}.card.orange{{background:#fff6e9;border-color:#ffdcb3}}.darkcard{{background:#0b345b;color:#fff;border-color:rgba(255,255,255,.12)}}.metric-card{{min-height:31mm}}.metric{{color:#0a67ff;font-size:21pt;font-weight:900;line-height:1.12;letter-spacing:-.05em}}.metric.orange{{color:#f37021}}.metric-label{{color:#65778b;font-size:8pt;line-height:1.45;margin-top:2mm}}.muted-card .metric{{font-size:15pt;color:#7d91a5}}.range-metric{{font-size:16pt}}.pill{{display:inline-block;border-radius:99px;padding:1.2mm 2.5mm;background:#e6f2ff;color:#0a67ff;font-size:7.5pt;font-weight:800}}.status{{display:inline-block;border-radius:99px;padding:1.6mm 3mm;background:#e6f2ff;color:#0a67ff;font-size:8.5pt;font-weight:900}}.callout{{padding:4mm;border-radius:3mm;background:#0a67ff;color:#fff;font-size:10.5pt;font-weight:800;line-height:1.55}}.callout.navy{{background:#0b345b;margin-top:4mm}}.cover{{padding:0;background:#082f58;color:#fff}}.cover:after{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 80% 15%,rgba(34,139,230,.28),transparent 30%),linear-gradient(160deg,transparent 48%,rgba(0,0,0,.18));z-index:0}}.cover-main{{position:relative;z-index:2;padding:18mm 16mm 0;height:188mm}}.cover .eyebrow{{color:#68b9ff}}.cover-title{{font-size:34pt;line-height:1.14;letter-spacing:-.065em;margin:17mm 0 6mm;font-weight:900}}.cover-sub{{font-size:14pt;line-height:1.58;color:#cce8ff;max-width:160mm}}.cover-facts{{display:flex;gap:3mm;flex-wrap:wrap;margin-top:12mm}}.cover-facts span{{border:1px solid rgba(255,255,255,.28);border-radius:99px;padding:2.2mm 4mm;background:rgba(255,255,255,.08);font-size:8.5pt}}.cover-gradient,.cover-photo{{position:absolute;left:0;right:0;bottom:0;height:110mm;z-index:1;background:radial-gradient(circle at 75% 45%,rgba(69,157,233,.16),transparent 32%),linear-gradient(180deg,#dbeeff 0%,#f7fbff 50%,#fff 100%)}}.cover-gradient:after,.cover-photo:after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,#082f58 0%,rgba(8,47,88,.12) 22%,rgba(255,255,255,0) 55%)}}.cover-photo img{{width:100%;height:100%;object-fit:cover}}.cover .brand{{z-index:3;color:#0a67ff}}.cover .page-no{{z-index:3}}.prologue-copy{{font-size:11pt;line-height:1.85;color:#29445e}}.analysis-list{{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-top:5mm}}.analysis-item{{display:grid;grid-template-columns:9mm 1fr;gap:2.5mm;background:#fff;border:1px solid #dce7f1;border-radius:3mm;padding:3.2mm}}.analysis-item b{{display:grid;place-items:center;width:8mm;height:8mm;border-radius:2mm;background:#0a67ff;color:#fff}}.analysis-item strong{{display:block;font-size:9.5pt}}.analysis-item small{{display:block;margin-top:1mm;color:#6b7d91;font-size:7.4pt;line-height:1.4}}.decision-band{{display:grid;grid-template-columns:1.15fr .85fr;gap:4mm;margin-top:5mm;padding:4mm;border-radius:3mm;background:#082f58;color:#fff}}.decision-band p{{font-size:8.5pt;line-height:1.5;color:#cbe7ff}}.decision-band strong{{font-size:14pt;line-height:1.45;letter-spacing:-.04em}}.value-frame{{margin-top:5mm}}.value-frame p,.evidence-copy p,.card p{{font-size:8.8pt;line-height:1.62;color:#4c647b}}.lead-small{{font-size:10pt!important}}.value-heading{{margin-top:5mm}}.ladder{{display:grid;grid-template-columns:repeat(3,1fr);gap:3mm}}.step{{border-radius:3mm;padding:3.6mm;border:1px solid #dbe7f1;border-top:2mm solid #0a67ff;background:#fff}}.step b{{display:block;font-size:11pt;margin:2mm 0}}.step p{{font-size:7.7pt;line-height:1.48;color:#60758a}}.table{{width:100%;border-collapse:collapse;font-size:8pt}}.table th{{background:#eaf3fb;color:#315571;text-align:left}}.table th,.table td{{padding:2.2mm 2mm;border-bottom:1px solid #e1e9f1}}.table-empty{{text-align:center;color:#6b7d91;padding:10mm!important}}.address-card{{display:flex;justify-content:space-between;align-items:center;padding:3mm 4mm;margin-bottom:3mm;border-radius:3mm;background:#edf6ff;border:1px solid #d5e9ff}}.address-card b{{font-size:10pt}}.address-card span{{font-size:8pt;color:#5d7185}}.route-grid{{display:grid;grid-template-columns:1fr 1fr;gap:3mm}}.route-grid.count-1{{grid-template-columns:1fr;max-width:125mm;margin:0 auto}}.route-card{{position:relative;height:80mm;overflow:hidden;border:1px solid #dbe7f1;border-radius:3mm;background:#fff}}.route-card img,.route-gradient{{width:100%;height:100%;object-fit:cover}}.route-gradient{{background:radial-gradient(circle at 70% 30%,rgba(10,103,255,.18),transparent 30%),linear-gradient(140deg,#eef7ff,#fff)}}.route-badge{{position:absolute;left:3mm;bottom:3mm;padding:2.2mm 3mm;border-radius:2mm;background:rgba(7,38,65,.9);color:#fff;min-width:42mm}}.route-badge b{{font-size:11pt}}.route-badge small{{display:block;color:#cde9ff;font-size:7.4pt;margin-top:1mm}}.location-empty{{height:174mm;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px solid #dbe7f1;border-radius:4mm;background:radial-gradient(circle at 50% 35%,rgba(10,103,255,.12),transparent 25%),linear-gradient(145deg,#eef7ff,#fff)}}.location-pin{{font-size:42pt;color:#0a67ff}}.location-empty h3{{font-size:20pt;margin:3mm 0}}.location-empty p{{font-size:11pt;color:#3c5873}}.location-empty span{{max-width:105mm;font-size:8.4pt;line-height:1.6;color:#6a7d90}}.note,.source-links{{font-size:7pt;line-height:1.45;color:#66798d}}.route-note{{margin-top:3mm}}.source-links{{margin-top:2mm}}.source-links a{{color:#0a67ff}}.compact-metrics{{margin-bottom:4mm}}.dominant-chart{{height:101mm}}.chart{{background:#fff;border:1px solid #d9e6f1;border-radius:3mm;padding:3mm}}.chart svg{{display:block;width:100%;height:100%}}.diagram svg{{width:100%;height:100%}}.evidence-copy{{margin-top:4mm}}.transaction-head{{grid-template-columns:.72fr 1.28fr}}.transaction-card{{margin-top:4mm}}.transaction-table{{font-size:8.5pt}}.trade-insights{{margin-top:4mm}}.trade-insights .card{{min-height:34mm;padding:3mm}}.trade-insights .h3{{font-size:9.5pt;margin:2mm 0 1mm}}.trade-insights p{{margin:0;font-size:7pt;line-height:1.45}}.activity-chart{{height:94mm}}.visual-empty{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#60758a}}.visual-empty b{{font-size:14pt;color:#0b2f55}}.visual-empty span{{max-width:110mm;margin-top:3mm;font-size:8.5pt;line-height:1.6}}.svg-label,.svg-legend{{font-family:"Noto Sans KR","Malgun Gothic",sans-serif;fill:#5d7185;font-size:10px}}.market-summary{{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-top:4mm}}.macro{{background:#fff;border:1px solid #dbe7f1;border-radius:3mm;padding:3mm}}.macro h4{{margin:0 0 1.5mm;font-size:9pt;color:#0b2f55}}.macro p{{margin:0;font-size:7.4pt;line-height:1.45;color:#60758a}}.listing-chart{{height:96mm}}.competition-band{{display:grid;grid-template-columns:.3fr .7fr;gap:3mm;align-items:center;margin-top:4mm;padding:3.5mm 4mm;border-radius:3mm;background:#0b345b;color:#fff}}.competition-band b{{font-size:9.5pt}}.competition-band span{{font-size:7.5pt;line-height:1.5;color:#cde9ff}}.final-page{{background:#082f58;color:#fff}}.final-page:before{{color:rgba(255,255,255,.055)}}.final-eyebrow{{color:#6dc0ff}}.final-decision{{font-size:24pt;line-height:1.3;letter-spacing:-.06em;font-weight:900;margin:5mm 0}}.final-decision em{{font-style:normal;color:#74c5ff}}.final-grid{{grid-template-columns:.9fr 1.1fr}}.light{{color:#fff}}.dark-table td{{color:#d7e8f7;border-color:rgba(255,255,255,.12)}}.dark-note{{font-size:7.2pt;line-height:1.45;color:#adc8df}}.next-title{{margin-top:4mm}}.checklist{{list-style:none;margin:0;padding:0;display:grid;gap:2mm}}.checklist li{{font-size:7.8pt;line-height:1.45;color:#4c647b}}.final-action{{margin-top:4mm;display:grid;grid-template-columns:.32fr .68fr;gap:3mm;align-items:center}}.final-action p{{margin:0}}.orange-callout{{background:#f37021;text-align:center}}.source-block{{margin-top:3mm;border-top:1px solid rgba(255,255,255,.15);padding-top:2mm}}.sources{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:1fr 1fr;gap:1.5mm 3mm}}.sources li{{display:grid;grid-template-columns:9mm 1fr auto;gap:1.5mm;align-items:start;font-size:6.4pt}}.sources li>b{{color:#69b8ff}}.sources strong,.sources small{{display:block}}.sources small{{color:#91a9c0}}.sources a,.sources li>span{{color:#7fc9ff;text-decoration:none}}.verification{{margin-top:2mm;font-size:6.3pt;color:#9dbbd3}}.closing-disclaimer{{font-size:6pt;line-height:1.35;color:#adc8df}}.final-page .brand,.final-page .page-no{{color:rgba(255,255,255,.72)}}.demo-badge{{position:absolute!important;right:12mm;top:8mm;z-index:20!important;padding:2mm 4mm;border-radius:99px;background:#fff1c9;color:#754b00;font-size:6.4pt;font-weight:900}}.gridline{{stroke:#e5e8ee;stroke-width:1}}.axisline{{stroke:#bac2ce;stroke-width:1.4}}.tick,.small-label{{fill:#727984;font-size:12px}}.label{{fill:#27303b;font-size:14px;font-weight:700}}.axis-title{{fill:#626a75;font-size:13px}}.value{{fill:#173c88;font-size:13px;font-weight:900}}.dot{{fill:#0a67ff}}.target-dot{{fill:#f37021;stroke:#fff;stroke-width:4}}.target-line{{stroke:#f37021;stroke-width:2;stroke-dasharray:7 5}}.target-pill{{fill:#f37021}}.pill-text{{fill:#fff;font-size:11px;font-weight:900}}.ask-range{{stroke:#f37021;stroke-width:12;stroke-linecap:round}}.legend{{fill:#57606c;font-size:12px}}.bar{{fill:#0a67ff}}.accent-bar{{fill:#f37021}}.bar-bg{{fill:#e8edf5}}.matrix-row{{fill:#f7f9fc;stroke:#d9dee7}}.status.ok{{fill:#dff3e9}}.status.warn{{fill:#fff0cf}}.status.hold{{fill:#eaf3fb}}.status-text{{fill:#26323d;font-size:11px;font-weight:900}}.no-data{{display:flex;height:100%;align-items:center;justify-content:center;color:#6d8195;font-weight:800}}@media print{{body{{background:#fff}}.sheet{{margin:0;box-shadow:none}}}}
'''
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="evidence-audit-sha256" content="{esc(audit.get("evidence_fingerprint", ""))}"><meta name="visible-payload-sha256" content="{esc(audit.get("visible_payload_fingerprint", ""))}"><meta name="asset-manifest-sha256" content="{esc(audit.get("asset_manifest_fingerprint", ""))}"><meta name="combined-release-sha256" content="{esc(audit.get("combined_release_fingerprint", ""))}"><meta name="derived-release-status" content="{esc(release_status)}"><meta name="report-type" content="standard"><meta name="report-engine" content="{ENGINE_ID}"><meta name="report-engine-version" content="{ENGINE_VERSION}"><meta name="communication-mode" content="{esc(data.get("communication_mode", "CUSTOMER_SALES"))}"><meta name="report-profile" content="EXTENDED_9"><meta name="conversion-goal" content="{esc(data.get("conversion_goal", "SITE_VISIT_CONSULTATION"))}"><meta name="customer-type" content="{esc(customer.get("role", ""))}"><meta name="evidence-mode" content="{esc(data.get("evidence_mode", ""))}"><title>{esc(target_name)} · {esc(mode_label)} 고객 상담 리포트</title><style>{css}</style></head><body>{"".join(pages)}<script>window.__REPORT_CHARTS_READY__ = true;</script></body></html>'''
