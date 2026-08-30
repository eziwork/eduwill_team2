# 아파트 시장자료 수집

아파트 매매의 실제자료 리포트에서 국토교통부 실거래와 네이버페이 부동산 현재 공개매물을 직접 수집할 때 사용한다. 두 자료는 같은 대상·면적을 보더라도 성격이 다르므로 원본, 정규화자료, 지표, 리포트에서 끝까지 분리한다.

## 0. 호출할 때마다 API 상태를 먼저 확인한다

다른 시장조사 전에 운영체제 공통 점검기를 실행한다.

```text
python scripts/check_molit_api.py
```

macOS에서 `python` 명령이 없으면 `python3`를 사용한다. 결과가 `KEY_MISSING`이면 공공데이터포털 인증키를 채팅으로 요청한다. 사용자가 입력한 키를 응답이나 명령줄에 재표시하지 말고 저장기를 먼저 실행한 뒤 표준입력으로 전달한다.

```text
python scripts/save_molit_api_key.py
```

Windows는 현재 사용자 DPAPI 저장소, macOS는 현재 사용자의 기본 키체인을 사용한다. 환경변수 `DATA_GO_KR_SERVICE_KEY`가 있으면 저장소보다 우선한다. Linux에서는 평문 파일 저장을 만들지 않고 이 환경변수만 사용한다.

점검 결과가 `CONNECTED`가 아니면 공식 수집을 시작하지 않는다. 인증 오류에는 새 키나 사용자 제공 공식 CSV·JSON을 요청한다. 연결 오류는 네트워크 권한과 엔드포인트 확인 후 한 번만 재시도한다.

## 1. 수집범위를 고정한다

[시장수집 요청 예시](../assets/apartment-market-request.example.json)를 복사해 다음을 확정한다.

- 단지명과 주소, 부동산 유형
- 매매 거래
- 전체 동 또는 특정 동
- 전체 면적 또는 실제 확인된 전용면적형
- 분석기간 `1`, `3`, `5`, `7`년 중 하나
- `RESEARCH_SAMPLE` 또는 서면권한 식별값이 있는 `AUTHORIZED_FULL`
- 국토부 `MOLIT`와 네이버페이 부동산 `NAVER_PAY_LAND` 중 사용할 출처

```powershell
pwsh -File scripts/validate_request_config.ps1 -ConfigPath path/to/apartment-market-request.json -OutputPath path/to/request-validation.json
```

결과가 `VALID`가 아니면 수집하지 않는다. 이미 확인한 내용은 다시 묻지 않고, 검증결과의 첫 차단질문만 사용자에게 묻는다.

## 2. 대상을 한 번만 확정한다

- 실제 검색결과로 단지명, 주소, 주택유형, 네이버 단지번호, 법정동코드를 확인한다.
- 사이트에서 실제 동·면적 선택지를 먼저 확인하고 요청값과 대조한다.
- 정수 전용면적은 `84.00 <= 면적 < 85.00`, 소수 입력은 ±0.05㎡를 기본 비교범위로 사용한다.
- 공급평수만 주어지면 공급면적 후보를 찾은 뒤 실제 공급·전용면적형을 확인한다.
- 한 번 확정한 대상·면적 매핑을 국토부와 네이버 자료에 공통으로 사용한다.

## 3. 국토부 실거래를 수집한다

내장 수집기는 아파트 매매만 지원한다. 다른 거래유형은 해당 공식 데이터셋과 수집경로를 먼저 확인한다.

1. [국토부 수집기 설정 예시](../assets/apartment-molit-collector.example.json)를 복사한다.
2. 실제 `lawd_cd`, 조회 시작·종료월, 단지명, 전용면적 범위, 공식 API 주소를 입력한다.
3. 먼저 `-DryRun`으로 범위를 확인한다.
4. 인증키는 명령줄에 넣지 않고 아래 저장기를 표준입력으로 실행한다.
5. 실제 수집 후 원본 XML, 전체 지역 정규화행, 대상행, 수집목록을 보존한다.

```powershell
pwsh -File scripts/collect_molit_apt_trade.ps1 -ConfigPath path/to/molit-config.json -DryRun
pwsh -File scripts/save_molit_api_key.ps1
pwsh -File scripts/collect_molit_apt_trade.ps1 -ConfigPath path/to/molit-config.json -OutputRoot path/to/data/molit
```

Windows 인증키 기본 저장경로는 `%USERPROFILE%\.codex\secrets\create-korean-real-estate-client-brief\molit-api-key.dpapi`이며 같은 Windows 사용자만 복호화할 수 있다. macOS에서는 서비스명 `eziwork-final.molit-api-key`로 현재 사용자의 기본 키체인에 저장한다. 키를 응답, 명령줄, 보고서, 로그에 다시 표시하지 않는다.

원본에는 취소·해제 거래도 보존하되 모든 가격·거래량 집계에서는 제외한다. 현재월은 잠정월로 분리하고 완결월끼리만 추이를 비교한다. 국토부 동 정보가 누락되면 단지·면적 집계와 동 확인행을 별도로 표시한다.

대상 필터 결과가 0건이면 원본 0건 응답과 수집목록을 보존하고 작업을 멈춘다. 사용자에게 국토교통부 내려받기 CSV·JSON, 정확한 법정동코드·유형·단지명·면적·기간, 또는 공식 조회범위 변경 동의를 요청한다. 답변 없이 범위를 넓히거나 유사 건물의 거래를 대상 거래로 바꾸지 않는다.

## macOS 실행조건

- Python 3: API 시작 점검과 키체인 저장
- PowerShell 7 (`pwsh`): 요청검증, 실거래 수집, 공통지표 계산
- Node.js와 Playwright 또는 Chrome·Edge·Chromium: PDF 렌더링
- `/usr/bin/security`: macOS 키체인 읽기·쓰기

PowerShell 스크립트는 `Join-Path`를 사용하고, Python·Node 스크립트는 운영체제 경로 모듈을 사용한다. Bash 전용 경로 확장이나 Windows 드라이브 문자를 macOS 명령에 넣지 않는다.

## 4. 네이버페이 부동산 현재 매물을 확인한다

브라우저에서 사용자가 요청한 단지 1곳과 면적형에 필요한 공개매물만 확인한다.

- 기본 수집은 `RESEARCH_SAMPLE`, 상세화면은 최대 10개다.
- 목록자료를 우선하고 최저·중앙·최고 대표가격, 서로 다른 면적형, 누락필드 확인에 필요한 상세만 연다.
- CAPTCHA, 로그인, 접근차단, 반복 타임아웃을 우회하지 않는다. 중단하고 사용자에게 저장 화면이나 내보내기 자료를 요청한다.
- 화면에서 이미 묶인 광고만 높은 신뢰도의 동일 매물그룹으로 본다. 규칙만으로 추정한 후보는 자동병합하지 않는다.
- 광고 원본을 먼저 보존한 뒤 중복후보를 정리한다.
- 현재 광고는 `snapshot_at` 한 시점의 `CURRENT_SNAPSHOT`이다. 과거 호가이력이나 거래완료로 바꾸어 해석하지 않는다.

[네이버 스냅샷 예시](../assets/naver-market-snapshot.example.json)의 최소 구조를 사용한다.

- `market_snapshot`: 원본 광고건수, 중복정리 후 후보수, 최저·중앙·최고 대표호가, 조회시각, 품질상태
- `listing_groups`: 그룹 ID, 동·층, 대표호가, 포함 광고수, 중복근거, 신뢰도
- 품질상태: `PASS`, `PARTIAL`, `SAMPLE_ONLY`, `FAILED`

광고건수와 고유 매물건수를 동일하게 표현하지 않는다. 표본·부분수집이면 고객 문장에도 `확인한 표본`이라고 표시한다.

## 5. 공통 지표를 계산한다

국토부 대상 정규화 JSON과 네이버 스냅샷 JSON을 입력해 공통지표를 한 번 계산한다.

```powershell
pwsh -File scripts/calculate_report_metrics.ps1 `
  -MolitRowsPath path/to/molit_apt_trade_target_rows.json `
  -NaverSnapshotPath path/to/naver_market_snapshot.json `
  -ReportDate YYYY-MM-DD `
  -FinalCompleteMonth YYYY-MM `
  -ReportId REPORT_ID `
  -HistoryYears 1 `
  -OutputPath path/to/report_metrics.json
```

계산기는 취소거래를 제외하고 완결월 통계, 기간별 거래건수·중위값, 최근 실거래, 현재 대표호가 범위, 실거래·호가 격차를 만든다. 이후 고객 리포트의 숫자·차트·문장·결론은 이 결과와 감사에 등록된 정규화자료에서만 가져온다.

## 6. 근거감사로 연결한다

- 국토부 원본·정규화·수집목록과 네이버 원본·스냅샷을 각각 파일로 보존한다.
- 각 파일의 SHA-256, 원문 URL, 조회조건, 기준일, 행수 대사를 `evidence_group`에 등록한다.
- 국토부 실거래는 `closed_or_reported_transactions`, 네이버 현재 공개매물은 `current_public_listings` 경로를 사용한다.
- 데이터가 0건이면 범위를 몰래 넓히지 않고 완료된 0건 응답을 보존한다.
- `PARTIAL`·`SAMPLE_ONLY`는 전체시장 주장에 사용하지 않는다.
- 감사결과가 `HOLD`이면 고객용 HTML·PDF를 만들지 않는다.
