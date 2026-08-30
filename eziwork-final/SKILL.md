---
name: eziwork-final
description: "한국 부동산의 시세·실거래·현재 공개매물·계약조건·권리 및 이용조건 자료를 수집·검증하고, 고객이 직접 읽는 상담용 HTML·PDF 리포트로 제작한다. 아파트 매매의 BUY·SELL 분석, 전세, 월세, 상가 임대, 토지 임대 브리핑에 사용한다. 실제자료 리포트와 명확히 표시된 교육용 예시를 지원하지만 감정평가·법률판단·보증승인·대출승인·무제한 사이트 수집에는 사용하지 않는다."
---

# 한국 부동산 고객 브리핑 제작

## 목적

고객의 구체적인 부동산 질문 하나를 근거가 확인되는 고객용 HTML·PDF 리포트로 만든다. 여러 거래유형에 공통으로 적용되는 제작 체계를 유지하되, 필요한 데이터·판단기준·문구·시각자료만 거래유형과 고객 관점에 맞게 분기한다.

## 시작 게이트: 국토교통부 API 상태를 먼저 확인한다

이 스킬이 호출될 때마다 다른 조사나 리포트 제작보다 먼저 `scripts/check_molit_api.py`를 실행한다. 이 점검은 인증키 존재 여부와 국토교통부 실거래 API의 실제 응답을 확인하며, 인증키 자체는 출력하지 않는다.

```text
python scripts/check_molit_api.py
```

실행환경에서 명령명이 `python3`이면 같은 스크립트를 `python3`로 실행한다. Codex Desktop에서 Python 경로를 찾지 못하면 `load_workspace_dependencies`로 번들 Python을 확인한다.

- `CONNECTED`: 채팅에 `국토교통부 API 연결 확인됨`이라고 짧게 알리고 다음 단계로 진행한다. 점검용 지역·월의 `probe_total_count`가 0이어도 연결 성공으로 본다.
- `KEY_MISSING`: 작업을 진행하지 말고 공공데이터포털에서 발급받은 국토교통부 실거래 API 인증키를 채팅으로 요청한다. 사용자가 채팅에 키를 입력해도 된다. 받은 값은 답변·명령줄·파일명·로그에 다시 표시하지 않고 `scripts/save_molit_api_key.py`의 표준입력으로 전달한다. Windows는 현재 사용자 DPAPI, macOS는 현재 사용자 키체인에 저장한 다음 점검을 한 번 다시 실행한다.
- `AUTH_OR_API_FAILED`: 인증키 갱신을 요청하거나 사용자가 제공한 공식 실거래 CSV·JSON을 요청한다. 실패를 숨기고 브라우저 표본을 공식 API 전체자료처럼 사용하지 않는다.
- `CONNECTION_FAILED` 또는 `INVALID_RESPONSE`: 네트워크 권한과 공식 엔드포인트를 확인한 뒤 한 번만 재시도한다. 계속 실패하면 공식 실거래 원본·CSV·JSON을 사용자에게 요청하고 API 상태를 QA에 남긴다.

대상 조건으로 실제 수집한 결과가 0건이면 0건 응답과 조회조건을 보존한다. 사용자에게 다음 중 필요한 자료를 채팅이나 파일로 요청한다.

- 국토교통부에서 내려받은 해당 대상의 실거래 CSV·JSON
- 정확한 법정동코드, 부동산 유형, 단지·건물명, 전용면적, 조회기간 정정
- 공식 조회범위를 변경해 다시 확인해도 된다는 답변

사용자가 자료를 제공하지 않거나 범위 변경에 동의하지 않으면 실거래 부분을 `자료 없음/확인 필요`로 유지한다. 거래행이나 가격을 만들어내지 않는다.

아파트 매매 리포트는 고객 관점을 다음 두 가지로만 구분한다.

- `BUY`: 매수 검토가격, 대체매물, 총비용, 협상 시작점과 상한, 매수 중단조건
- `SELL`: 출시가격, 경쟁매물, 문의·방문 반응, 가격 조정구간과 시점, 매도 실행기준

아파트의 공통 시장분석은 한 번만 수행한다. BUY와 SELL에 따라 달라지는 것은 질문의 표현, 근거의 해석, 결론과 다음 행동이다. 기존의 `BUY / SELL / USE / OPERATE` 4분류는 이 경로에서 사용하지 않는다.

지원 거래유형:

- `sale`: 매매
- `jeonse`: 전세
- `monthly_rent`: 월세
- `commercial_lease`: 상가 임대
- `land_lease`: 토지 임대

## 필요한 자료만 선택해서 읽기

모든 참고문서를 한꺼번에 읽지 않는다. 현재 요청에 필요한 자료만 다음 순서로 선택한다.

1. 누락된 입력을 질문하기 전 [상담 입력 절차](references/interview-flow.md)를 읽는다.
2. 데이터를 수집하거나 분석하기 전 [조사 및 품질기준](references/research-and-quality.md)을 읽는다.
   - 아파트 매매 실거래와 현재 공개매물을 직접 수집할 때는 [아파트 시장자료 수집](references/apartment-market-data-collection.md)도 읽는다.
3. 실제자료 리포트 또는 배포 판정을 만들기 전 [근거 감사 스키마](references/evidence-audit-schema.md)를 읽는다.
4. 고객용 문장과 HTML을 작성하기 전 [문장 및 디자인 규칙](references/report-writing-and-design.md)을 읽는다.
   - 투자분석·칼럼형·매거진형 요청이면 [매거진 투자분석 스타일](references/magazine-investment-style.md)도 읽는다.
   - 아파트 BUY·SELL이면 [체크포인트 편집형 템플릿](references/checkpoint-editorial-template.md)을 읽는다. 이것이 아파트 매매의 기본 디자인이다.
5. 아래에서 현재 거래유형과 일치하는 문서 하나만 읽는다.
   - [매매](references/mode-sale.md)
   - [전세](references/mode-jeonse.md)
   - [월세](references/mode-monthly-rent.md)
   - [상가 임대](references/mode-commercial-lease.md)
   - [토지 임대](references/mode-land-lease.md)
6. 독립 검토가 가능하고 허용됐거나 사용자가 별도 감사를 요청했을 때만 [독립 근거 검토](references/independent-evidence-review.md)를 읽는다.

주요 입력·템플릿 자산:

- 일반 리포트 입력 예시: [report-request.example.json](assets/report-request.example.json)
- 일반 콘텐츠 골격: [client-brief-template.md](assets/client-brief-template.md)
- 아파트 시장수집 요청 예시: [apartment-market-request.example.json](assets/apartment-market-request.example.json)
- 국토부 수집기 설정 예시: [apartment-molit-collector.example.json](assets/apartment-molit-collector.example.json)
- 국토부 정규화행 예시: [molit-target-rows.example.json](assets/molit-target-rows.example.json)
- 네이버 공개매물 스냅샷 예시: [naver-market-snapshot.example.json](assets/naver-market-snapshot.example.json)
- 아파트 BUY·SELL 입력 예시: [checkpoint-editorial.example.json](assets/checkpoint-editorial.example.json)
- 아파트 기준 HTML: [checkpoint-editorial-reference.html](assets/checkpoint-editorial-reference.html)
- 아파트 시각검수 기준 PDF: [checkpoint-editorial-reference.pdf](assets/checkpoint-editorial-reference.pdf)
- 내부 데이터 QA 기록: [source-data-qa-report-template.md](assets/source-data-qa-report-template.md)

기준 HTML·PDF의 단지명, 이미지, 지도, 날짜, 숫자와 결론은 디자인 참고자료일 뿐이다. 새 리포트의 근거로 복사하지 않는다.

## 반드시 지킬 원칙

1. 최종 리포트는 고객이 직접 읽는 문서다. `고객에게는 이렇게 설명합니다`, `중개사가 승인`, `고객 전달 전`, `영업용 멘트`, `스킬 설계용` 같은 내부 표현을 넣지 않는다.
2. `체결 또는 신고된 거래`, `현재 공개 매물`, `소유자·중개사 확인정보`, `법률·행정 확인사항`을 분리한다. 서로 성격이 다른 숫자를 합산하거나 평균내 임의의 시세를 만들지 않는다.
3. 시점에 따라 달라지는 숫자·상태·지도에는 출처, 공개된 경우 원문 URL, 기준일을 표시한다. 비공개 확인기록은 `내부 확인 기록 · 외부 링크 없음`으로 적는다.
4. 표시한 값을 원자료까지 추적할 수 있을 때만 `actual`을 사용한다. 임의값이나 구조시험용 값은 `demo`로 지정하고 모든 페이지에 `교육용 예시 · 실제 시세가 아님`을 표시한다.
5. 감정평가액, 법적 안전성, 대출승인, 보증가입, 허용용도, 사업 적합성을 확정적으로 말하지 않는다. 확인된 사실, 미확인사항, 다음 확인행동을 분리한다.
6. 네이버페이 부동산은 사용자가 실행하는 단지 1곳 중심의 제한적 공개매물 확인에만 사용한다. 전체 서비스 수집, 로그인·CAPTCHA·차단 우회, 광고 수를 고유 매물 수로 단정하는 행동을 금지한다.
7. 아파트 매매 실거래·호가 분석은 이 스킬의 내장 수집·검증 절차를 사용한다. 다른 거래유형은 공식 데이터가 해당 거래·부동산 유형을 지원하는지 먼저 확인한다. 확실하지 않으면 사용자 제공 정규화 자료를 사용하거나 `확인 필요`로 남기며 행을 만들어내지 않는다.
8. PDF에는 정적 지도 이미지나 화면 캡처를 사용한다. iframe, 지도 조작버튼, 검색창과 이동 UI를 인쇄물에 넣지 않는다. 브라우저용 지도 링크는 별도로 제공할 수 있다.
9. 아파트 BUY·SELL은 9페이지 체크포인트 편집형을 기본으로 한다. 다른 거래유형은 의사결정에 필요한 근거에 따라 페이지 수를 조정한다. 아파트 기본 페이지 수를 변경하려면 실제 근거상 필요하거나 사용자가 명시적으로 요청해야 하며 QA에 변경 사유를 기록한다.
10. 개인정보, 비공개 소유자 정보, 토큰, API 키, 불필요한 동·호 식별정보를 노출하지 않는다.
11. 사람이 입력한 배포결과를 신뢰하지 않는다. 결정론적 근거 감사가 파일 해시, 수집범위, 건수 대사, 계산식, 주장 연결관계를 검사해 `PASS`, `PASS WITH CONDITIONS`, `HOLD`를 산출한다.
12. `actual` 리포트의 수치·문장·차트·결론은 등록된 주장과 연결한다. 계산 주장은 재현 가능한 계산기록과 연결하고, 모든 주장은 출처와 근거그룹까지 역추적할 수 있어야 한다.
13. 아파트 체크포인트형은 완료된 실거래, 현재 공개매물, 개별 매물조건을 시각적으로 분리한다. 독점적이거나 근거가 공개되지 않은 적정가 공식을 기본값으로 재현하지 않는다. 모든 입력·가정·계수·계산을 추적할 수 있고 감정평가로 표현하지 않을 때만 별도 공식을 추가한다.
14. 사용자가 다른 디자인을 명시하지 않는 한 체크포인트형 HTML·PDF를 아파트 시각 기준으로 사용한다. 실험용 과거 템플릿으로 임의 전환하지 않는다.

## 제작 절차

### 1. 질문을 고정한다

[상담 입력 절차](references/interview-flow.md)에 따라 다음 항목을 확보하거나 합리적으로 추론한다.

- 거래유형 하나
- 대상 부동산과 비교단위
- 고객 역할과 실제 의사결정 질문
- 분석기간 또는 계약조건
- `actual` 또는 `demo`
- 브랜드 정보와 출력위치

이미 대화나 파일에 있는 사실은 다시 묻지 않는다. 한 번에 질문은 최대 세 개로 제한한다. 결과를 크게 바꾸지 않는 가정은 가정임을 밝히고 진행한다.

### 2. 거래유형과 고객 관점을 선택한다

일치하는 거래유형 문서 하나만 읽고, 해당 문서의 필수근거·계산·시각자료·금지표현을 적용한다. 임대·상가·토지 리포트에 아파트 매매용 차트를 억지로 사용하지 않는다.

아파트 매매라면 `customer_type`도 고정한다.

- 지불 여부와 매수 상한을 결정하면 `BUY`
- 출시가격과 조정시점을 결정하면 `SELL`
- 한 고객용 PDF에 BUY와 SELL 결론을 함께 넣지 않는다.

### 3. 근거를 수집하고 정규화한다

[조사 및 품질기준](references/research-and-quality.md)을 따른다. 자료를 다음 네 경로로 분리한다.

- `closed_or_reported_transactions`: 체결 또는 신고된 거래
- `current_public_listings`: 현재 공개매물
- `official_rules_and_status`: 공식 법률·행정·제도 상태
- `field_or_private_confirmations`: 현장 또는 비공개 확인기록

대상 필터, 조회시각, 원문 URL, 단위, 제외기준, 한계를 기록한다. 중복 제거는 규칙을 먼저 밝힌 뒤 수행한다. 결과가 0건인 기간을 숨기거나 임의로 조회범위를 넓히지 않는다.

`actual`에서는 원본 또는 정규화 파일, SHA-256, 예정·완료 기간과 페이지, 가능한 경우 원문 총건수, 행 대사, 파싱 실패, 제외내역, 미해결 오류까지 보존한다. 구조는 [근거 감사 스키마](references/evidence-audit-schema.md)를 따른다.

아파트 매매를 직접 조사할 때는 [아파트 시장자료 수집](references/apartment-market-data-collection.md)에 따라 다음 내부 도구를 사용한다.

- `scripts/check_molit_api.py`: Windows·macOS 공통 국토부 인증·연결 시작 점검
- `scripts/save_molit_api_key.py`: 표준입력으로 받은 키를 Windows DPAPI 또는 macOS 키체인에 저장
- `scripts/validate_request_config.ps1`: 단지·동·면적·기간·수집권한 검증
- `scripts/save_molit_api_key.ps1`: PowerShell 환경의 호환 인증키 저장기
- `scripts/collect_molit_apt_trade.ps1`: 국토부 아파트 매매 실거래 원본·정규화·수집목록 생성
- `scripts/calculate_report_metrics.ps1`: 실거래와 현재 공개매물 스냅샷을 분리한 지표 계산

### 4. 의사결정 순서로 분석한다

각 질문은 다음 순서로 답한다.

1. `지금 확인된 사실`
2. `그 사실이 질문에 의미하는 것`
3. `아직 확인되지 않은 것`
4. `계약·상담 전에 할 다음 행동`

하나의 숫자를 뒷받침할 수 없으면 범위와 비교사례를 사용한다. 계산명과 단위를 표시한다. 표본이 부족하면 추세를 그리지 않고 `자료 부족`으로 표현한다.

### 5. 고객용 문장을 작성한다

[문장 및 디자인 규칙](references/report-writing-and-design.md)을 적용한다.

- 제목은 짧은 질문형 또는 결론형으로 쓴다.
- 각 페이지 첫 문장에서 핵심 답을 제시한다.
- 전문용어는 처음 등장할 때 풀어쓴다.
- `확인됩니다`, `비교할 수 있습니다`, `추가 확인이 필요합니다`처럼 차분한 상담 어조를 사용한다.
- 과장, 매수·계약 압박, 확정적 전망, 제작과정 설명을 피한다.
- `한눈에 설명`은 짧은 핵심결론 라벨로만 사용한다.

### 6. HTML과 PDF를 생성한다

스킬 폴더에서 예제 JSON을 복사해 입력값을 채운 뒤 실행한다.

일반 리포트:

```powershell
python scripts/audit_evidence.py path/to/request.json --output path/to/evidence-audit.json
python scripts/validate_request.py path/to/request.json
python scripts/build_report.py path/to/request.json --output path/to/report.html --audit-output path/to/evidence-audit.json
python scripts/validate_report.py path/to/report.html --request path/to/request.json
node scripts/render_report.mjs --input path/to/report.html --output path/to/report.pdf
```

투자분석·매거진형:

```powershell
python scripts/build_magazine_report.py path/to/request.json --output path/to/report.html --audit-output path/to/evidence-audit.json
```

아파트 체크포인트형:

```powershell
python scripts/build_checkpoint_report.py path/to/request.json --customer-type BUY --output path/to/report.html --audit-output path/to/evidence-audit.json
python scripts/build_checkpoint_report.py path/to/request.json --customer-type SELL --output path/to/report.html --audit-output path/to/evidence-audit.json
```

실제 고객 리포트는 선택한 관점 하나만 생성한다. 위 두 명령은 사용 가능한 경로를 설명하거나 템플릿 QA를 할 때만 함께 제시한다.

Codex Desktop에서 `python` 또는 `node`가 PATH에 없으면 `load_workspace_dependencies`로 번들 실행경로를 확인한다. 렌더러는 현재 작업공간 또는 `CODEX_NODE_MODULES`의 Playwright와 설치된 Chrome·Chromium을 사용한다.

Windows와 macOS 모두 경로를 문자열로 조립하지 말고 Python의 `pathlib.Path`, PowerShell의 `Join-Path`, Node의 `path`를 사용한다. macOS에서 시장수집 PowerShell 스크립트를 실행할 때는 PowerShell 7의 `pwsh`가 필요하다. 인증키는 macOS 키체인, Windows DPAPI에 보관한다. PDF 렌더러는 Playwright 번들 브라우저를 우선 사용하고, 설치된 Chrome·Edge·Chromium의 Windows 및 macOS 표준 경로를 대체 경로로 확인한다.

일반 생성기는 `band`, `bar`, `line`, `scatter`, `matrix`, `image` 시각화를 지원한다. 인라인 SVG 또는 로컬 이미지 자산을 사용하고 외부 차트 프레임워크나 네트워크 의존성을 새로 추가하지 않는다.

매거진 생성기는 동일한 근거 스키마에 `prologue`, `map`, `chart`, `matrix` 레이아웃을 추가한다. 수익을 예측하는 대신 가격 위치, 유동성, 보유비용 입력값, 하락조건과 미확인사항을 보여준다.

체크포인트 생성기는 표지, 프롤로그 2페이지, 대상·지도, 가격 위치, 실거래 분포, 거래 활력, 현재 경쟁매물, 결론으로 구성된 9페이지 A4 편집형을 만든다. 네 개 근거 페이지는 공통이며 BUY·SELL에 따라 질문·해석·행동만 변경한다.

### 7. 배포 전 최종검사를 수행한다

다음 조건을 모두 충족해야 배포한다.

- 거래유형, 대상, 역할, 질문, 기준일, 자료모드가 명시되어 있다.
- 카드·차트·본문·결론의 수치가 일치한다.
- 모든 데이터그룹이 출처기록과 연결되어 있다.
- 실거래와 현재 공개매물이 분리되어 있다.
- 권리·보증·허가·용도·현장조건의 미확인사항이 표시되어 있다.
- 교육용 숫자가 현재 시세처럼 보이지 않는다.
- 자리표시자, 빈 링크, 깨진 로컬 이미지, iframe, 내부 제작문구가 남아 있지 않다.
- HTML 검증을 통과했다.
- PDF 렌더링 후 모든 페이지를 직접 시각검수했다.
- 현재 운영체제에서 API 시작 점검 결과와 Python·PowerShell·Node·브라우저 실행 여부를 QA에 기록했다.

배포결과는 감사가 산출한 `PASS`, `PASS WITH CONDITIONS`, `HOLD`만 사용한다. `HOLD`이면 생성기가 고객용 HTML을 거부하도록 유지하고 이를 우회하거나 PDF로 변환하지 않는다.

## 완료 보고

완성된 HTML, PDF, 근거감사·QA 기록의 링크를 먼저 제시한다. 거래유형, 대상, 기준일, `actual` 또는 `demo`, 배포결과, 남은 현장확인 항목만 간단히 적는다. 채팅에서 리포트 전문을 반복하지 않는다.
