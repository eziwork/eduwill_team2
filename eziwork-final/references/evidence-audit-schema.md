# 근거 감사 스키마

`actual` 요청파일을 준비하기 전에 읽는다. 고객 리포트는 `scripts/audit_evidence.py`가 산출한 감사결과로만 생성한다. 배포결과를 손으로 입력하지 않는다.

## 근거 연결구조

모든 고객용 사실은 다음 연결을 따라야 한다.

`source → evidence_group → 필요한 경우 calculation → claim → metric/copy/chart/conclusion`

연결단계마다 안정적인 ID를 사용한다. 하나의 주장은 여러 출처나 근거그룹을 인용할 수 있지만, 출처가 있는 것처럼 보이게 하려고 무관한 출처를 붙이지 않는다.

## 출처 레코드

`actual` 모드의 필수 필드:

- `id`: 안정적인 출처 ID
- `grade`: `A`, `B`, `C` 또는 명확히 정의한 다른 등급
- `lane`: `closed_or_reported_transactions`, `current_public_listings`, `official_rules_and_status`, `field_or_private_confirmations` 중 하나
- `name`: 운영기관과 자료·페이지명
- `url`: 원문 URL 또는 정확히 `내부 확인 기록 · 외부 링크 없음`
- `as_of`: 자료 기준일
- `retrieved_at`: 가능한 경우 시간대를 포함한 조회일시
- `query_conditions`: 대상, 거래유형, 기간, 면적, 재현에 필요한 모든 필터
- `scope`: 이 출처가 확인할 수 있는 범위
- `limitation`: 확인할 수 없는 범위

## 근거그룹

각 그룹의 필수 필드:

- `id`, `lane`, `source_ids`, `required_for_question`
- `status`: `COMPLETE`, `ZERO_RESULT`, `SAMPLE_ONLY`, `PARTIAL`, `BLOCKED`, `NOT_APPLICABLE` 중 하나
- `coverage`: 예정·완료 기간, 필요한 경우 예정·수집 페이지, 비교 가능한 원문·수집 총건수
- `counts`: `raw_rows`, `normalized_rows`, `excluded_rows`, `parse_failed_rows`, `used_rows`
- `exclusions`: 제외사유와 건수
- `errors`: 미해결 수집·파싱 오류
- `artifacts`: 원본·정규화 파일의 로컬 경로와 대소문자 어느 형식이든 유효한 SHA-256
- `completeness_basis`: 해당 상태가 타당한 이유

다음 건수 대사식은 필수다.

`raw_rows = normalized_rows + excluded_rows + parse_failed_rows`

또한 `used_rows <= normalized_rows`여야 한다. `ZERO_RESULT`는 예정한 모든 조회를 완료하고 0건 응답을 보존했을 때만 유효하다. `SAMPLE_ONLY`와 `PARTIAL`은 전체 시장의 재고, 범위, 순위를 주장하는 근거가 될 수 없다.

`COMPLETE`와 `ZERO_RESULT`에는 완결성 근거가 최소 하나 필요하다. 기간목록 일치, 페이지수 일치, 원문 총건수 일치, 또는 유한한 단일범위 조회의 `coverage.scope_exhausted: true`를 사용한다. 모든 행수가 0이면 `COMPLETE`가 아니라 `ZERO_RESULT`를 사용한다.

## 계산 레코드

필수 필드:

- `id`
- `operation`: `count`, `median`, `min`, `max`, `sum`, `ratio`, `percent_change`, `midrank_percentile` 중 하나
- `inputs`
- `output`
- `display_value`: 지표나 문장에 사용할 정확한 표시값
- `input_artifact_path`: 주장 근거그룹에 등록된 JSON 파일
- 선택 `input_key`: JSON 안의 계산 입력객체를 가리키는 점 표기 경로
- 선택 `tolerance`
- `unit`, `rounding`

감사 스크립트는 먼저 `inputs`가 SHA-256 검증 JSON에서 선택한 객체와 정확히 일치하는지 확인하고 출력을 재계산한다. 설명식만 저장하지 말고 원 수치입력을 저장한다. 수집원본이 HTML, XML, CSV, 화면이면 이를 보존하고 정규화 JSON 계산입력 파일을 별도로 만들어 둘 다 근거그룹에 등록한다.

## 주장 레코드

필수 필드:

- `id`
- `kind`: `direct`, `calculated`, `interpretive` 중 하나
- `statement`: 숫자와 범위를 포함한 완전한 주장
- `display_value`: 지표카드가 표시할 때 필수
- `source_ids`, `evidence_group_ids`
- 계산주장의 `calculation_id`
- `scope`: `complete`, `sample` 또는 다른 명시적 범위
- 불완전 근거를 사용할 때의 `limitation`

`SAMPLE_ONLY` 또는 `PARTIAL`을 쓰면 `scope`를 `sample`로 지정하고 주장에 `확인한 표본`, `조회한 표본`, `표본 매물`, `표본 자료` 중 알맞은 표현과 한계를 표시한다. 지키지 않으면 감사결과는 `HOLD`다.

## 화면 구성요소 연결

- 모든 지표에는 `claim_id` 하나가 있으며 `value`는 해당 주장의 `display_value`와 정확히 일치한다.
- `overview.claim_ids`는 개요의 모든 숫자문장을 덮는다.
- 모든 섹션에 `claim_ids`가 있고 `visual.claim_ids`는 표시한 모든 숫자를 덮는다.
- `summary.claim_ids`가 있으며 요약카드마다 `claim_id` 하나를 둔다.

감사는 연결된 주장문, 표시값, 계산 입력·출력에 없는 고객용 숫자를 거부한다. 카드, 차트, 본문, 결론이 서로 달라지는 일을 막기 위한 규칙이다.

## 감사 산출 배포결과

- `HOLD`: 파일 누락·변경, 해시 불일치, 건수 미대사, 필수범위 미완료, 미해결 수집오류, 계산 불일치, 근거 없는 숫자, 깨진 주장연결, 필수근거 차단
- `PASS WITH CONDITIONS`: 오류는 없지만 명시한 표본·부분 근거를 표본범위 주장에만 사용
- `PASS`: 필수그룹이 모두 완결되거나 적절히 기록된 0건이며 모든 계산·주장 연결이 통과

생성기는 감사결과가 `HOLD`인 고객 HTML 생성을 거부한다. 보류된 요청에서 PDF를 만들지 않는다.
