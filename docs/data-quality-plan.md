# Data Quality Plan

- 생성 시각: `2026-04-11T16:05:37.910248+00:00`
- 우선순위: `P2`
- 데이터 품질 점수: `96`
- 가장 약한 축: `추적성`
- Governance: `medium`
- Primary Motion: `conversion`

## 현재 이슈

- 현재 설정상 즉시 차단 이슈 없음. 운영 지표와 freshness SLA만 명시하면 됨

## 필수 신호

- 실시간 대기시간·예약 슬롯·운영 상태
- 티켓 가격·날씨·시즈널리티 보조 신호
- 장소·시설·서비스 단위 canonical queue key

## 품질 게이트

- 관측 시각과 이벤트 시각을 별도 필드로 유지
- 대기시간 단위와 timezone을 명시
- 예측용 외부 변수는 실제 대기시간과 분리 저장

## 다음 구현 순서

- 티켓 가격, 예약 슬롯, 날씨 source를 예측 보조 레이어로 연결
- 장소/시설 canonicalization rule을 추가
- 대기시간 outlier와 stale reading 검증을 리포트에 포함

## 운영 규칙

- 원문 URL, 수집일, 이벤트 발생일은 별도 필드로 유지한다.
- 공식 source와 커뮤니티/시장 source를 같은 신뢰 등급으로 병합하지 않는다.
- collector가 인증키나 네트워크 제한으로 skip되면 실패를 숨기지 말고 skip 사유를 기록한다.
- 이 문서는 `scripts/build_data_quality_review.py --write-repo-plans`로 재생성한다.
