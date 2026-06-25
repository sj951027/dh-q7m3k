# 사전등록 — 저변동 트랙 lv_a~d·lv_a3 (2026-06-25)

> 골대 고정용. 결과 보고 기준을 나중에 바꾸지 않으려 **미리** 못 박는다.
> PROJECT_KNOWLEDGE.md §11(40거래일·h=20d·부트스트랩 CI·다중검정)·§11-A(post-hoc forward-only)
> 를 상속. 상세 설계는 LOWVOL_TRACK_DESIGN.md.

---

## A. 트랙 정체성

- v3(과매도 중소형)·large(대형 가치)와 **완전 분리된 제3 트랙**. 별도 테이블 `lowvol_scores`,
  전용 페이지 `docs/lowvol.html`, 전용 텔레그램(`notify_lowvol_test.py`). v3·large 산출물 불변.
- 발견 경로: 18거래일(0602~0624) history.db 오프라인 분석에서 v3 한계를 추적하다 발견한
  신호 3종(저변동·단기반전·ROE). **사후(post-hoc) 발견 → forward-only.**

## B. 모델 스펙 (동결 — 불변규칙 2)

순위합 = run(=run×market) 내 cross-sectional 백분위 합. 핵심팩터 실측 필수(NaN 제외),
보조팩터 NaN은 0.5 중립. 부호: 저변동·지난주패자=작은값 선호(asc F), ROE·낙폭=큰값 선호(asc T).

| model_id | 핵심팩터 | 구성 | 유니버스 | 노출 |
|---|---|---|---|---|
| `lv_a` | realized_vol | 저변동+ROE+반전 | 과매도30~70·유동≥5억 | **텔레그램+HTML(테스트)** |
| `lv_b` | realized_vol | 저변동+ROE | 동 | shadow |
| `lv_c` | drawdown | 낙폭+ROE+반전 | 동 | shadow |
| `lv_d` | drawdown | 낙폭+ROE | 동 | shadow |
| `lv_a3` | realized_vol | 저변동+ROE+반전 | 과매도**30~60**·유동≥5억 | shadow |

- 유동성 하한 5억 = 중간과매도 중앙값 10.4억의 절반(하위25%=2.8억 위). 일평균 439종목. **분포 근거(매직넘버 아님).**
- 과매도 컷 30~70: 극단(70+)은 반전 IC 반토막(−0.287→−0.124)이라 제외. 30 하한은 유동성하한이
  이미 저과매도를 걸러 사실상 무영향(검증).
- lv_a3 = lv_a와 점수식 동일, 유니버스만 상한 60(민감도서 IC 약간↑·n 절반). lv_a와 forward 비교.

## C. 발견 경로 정직성 (중요)

- 신호 3종은 v3 진단 중 **여러 후보(stage3 전 수치팩터)를 훑어 고른 사후 선택.** in-sample IC는
  **증거가 아니라 가설.** OOS 판정엔 등록일(2026-06-25) 이후 run만 사용.
- 노출(lv_a)도 "검증된 모델"이 아니라 **18일 in-sample 견고성 1위**일 뿐. 텔레그램·HTML 전체가
  '테스트·관측·매수신호 아님'으로 도배. 점수↑=선호지 매수 아님.

## D. 판정 기준 (사전등록)

- **판정 시점**: 등록일 이후 **OOS 40거래일** 누적 후 1차 판정. 그 전 노이즈.
- **주력 지표**: 전 유니버스 Spearman IC, h=5d(반전 포함 모델) / h=20d(저변동·ROE·낙폭).
  - ⚠️ **realized_vol 커버리지 ~43%라 lv_a/b의 h=20d는 현재 표본 0** → forward로 쌓여야 장기 판정 가능.
    그 전까지 저변동 장기성은 미검증. 낙폭(lv_c/d)은 h=20d 측정 가능(커버리지 100%).
- **다중검정**: 모델 5개(lv_a~d·lv_a3) → Bonferroni 분모 5. CI는 ≈99%(0.05/5)로 올리거나 별도
  호라이즌 재현 시만 최종 채택. 못 넘으면 '기움'까지만.
- **무판정도 결론**: 40일 차도 기준 미달이면 **노출 유지하되 가중 안 함**(정상). 과적합 방지.

## E. 발견기간 in-sample 참고치 (증거 아님 — 가설)

> 아래는 발견표본 수치라 **판정 근거로 쓰지 않는다.** 등록 후 OOS와 비교해 과적합 정도만 본다.

- h=5d 시장초과 IC(좁은 유니버스): lv_a 0.226, lv_a3 0.234, lv_b 0.191, lv_c 0.142, lv_d 0.158.
- lv_a 견고성(2차 검증): 코스피 0.251/코스닥 0.211, 전반 0.242/후반 0.226, 5분위 단조(−1.02→+2.13),
  유니버스민감도 0.2~0.25. → 18일 안에서 견고하나 **forward에서 줄어드는 게 정상.**
- 결합 교훈: 저변동·반전을 **AND 아니라 순위합**으로 더해야 효과(AND는 모순집합=추가하락).
  낙폭·OCF·모멘텀 추가는 가산가치 0(중복정보) → 3팩터가 스위트스폿.

## F. 운영

- `.bat`(run_and_diversify) 2.86 lowvol_score 적재(증분) → 2.87 build_lowvol_filter(lv_a CSV)
  → 4b notify_lowvol_test(정상 배포일만). 전부 **비치명**(실패해도 챔피언 배포 안 막음).
- 최초 1회: `python lowvol_score.py --full`(36178행) + `python build_lowvol_filter.py`.
- 코드는 PUSH_ALLOWLIST(docs)에 안 걸리므로 **수동 `git add lowvol_score.py …` 커밋 필요.**
  docs/lowvol.html·docs/latest_*_lowvol.csv는 자동 push. 루트 사본은 gitignore.
