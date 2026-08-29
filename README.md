# EZIWORK 부동산 시세·시장조사 통합 스킬

한국 부동산의 공식 실거래와 현재 공개매물 또는 중개사가 제공한 후보자료를 분리해 분석하고, 고객용 9페이지 HTML/PDF 브리핑을 만드는 Codex Agent Skill입니다. 표준 보고서는 `EZIWORK_GOLDEN_V3` 엔진 버전 `3.1.0`으로 생성됩니다.

이 저장소의 `eziwork-real-estate-market-brief` 폴더 전체가 하나의 설치 가능한 스킬입니다. 교육용 예제는 API 키 없이 실행되며, 실제 국토교통부 자료를 수집하려면 대상 데이터셋의 활용승인과 서비스키가 필요합니다.

## 설치

`eziwork-real-estate-market-brief` 폴더를 다음 위치에 복사한 뒤 새 Codex 작업에서 호출합니다.

```text
%USERPROFILE%\.codex\skills\eziwork-real-estate-market-brief
```

```text
$eziwork-real-estate-market-brief
잠실엘스 전용 84㎡ 매매를 최근 3년 기준으로 분석해 고객용 PDF로 만들어줘.
```

빠른 교육용 실행은 스킬 폴더에서 다음 명령을 사용합니다.

```powershell
pwsh -NoProfile -File scripts/run_report.ps1 `
  -IntakePath assets/demo-apartment.json `
  -ReportRoot reports/demo-apartment
```

## 지원범위

| 물건유형 | 매매 | 전세 | 월세 |
|---|:---:|:---:|:---:|
| 아파트 | 공식 RTMS | 공식 RTMS | 공식 RTMS |
| 연립·다세대 | 공식 RTMS | 공식 RTMS | 공식 RTMS |
| 단독·다가구 | 공식 RTMS | 공식 RTMS | 공식 RTMS |
| 오피스텔 | 공식 RTMS | 공식 RTMS | 공식 RTMS |
| 토지 | 공식 RTMS | 제공자료만 | 제공자료만 |
| 상업·업무용 | 공식 RTMS | 제공자료만 | 제공자료만 |

네이버페이 부동산 자료는 인앱 브라우저에서 확인한 제한된 표본이나 사용자가 제공한 JSON/CSV만 사용합니다. 전수수집, 차단 우회, 비공개 API 호출은 포함하지 않습니다.

## 기본 처리 흐름

```text
intake.json
  -> source-plan.json
  -> raw/normalized evidence
  -> metrics.json + matching.json
  -> report-request.json + evidence-audit.json
  -> report.html -> report.pdf -> review images
```

리포트에 표시되는 실거래, 현재 호가, 고객·중개사 확인정보는 서로 다른 근거로 유지됩니다. 결과물은 감정평가, 법률·세무 판단, 대출·보증 승인 또는 투자수익 보장이 아닙니다.

## 기여

- 김형석: 통합 입력 범위, 출처계획, 국토교통부 유형별 수집·정규화, 인증정보 보호 구조
- 김용석: 고객 의사결정형 리포트, 증거감사, HTML/PDF 디자인·검증 구조
- EZIWORK: 교육용 단일 입력, 통합 변환기, 매물조건 매칭, 9페이지 Golden V3 실행 흐름

이 저장소는 에듀윌 강의 참여자 공유용입니다. 별도 공개 라이선스는 포함하지 않습니다.
