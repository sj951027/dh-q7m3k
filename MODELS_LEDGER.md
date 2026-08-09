# MODELS_LEDGER — 전 트랙 모델 원장 (2026-08-09 기준)

> 용도: 세션 시작용 한눈 인덱스(프로젝트 지식 업로드용). **정본은 각 PREREGISTER_*.md(골대)와
> VERDICT_*.md(판정), 등록일 단일소스는 checkup.py REG_DATE.** 이 문서와 정본이 어긋나면 정본이 이긴다.
> 갱신 규칙: 모델 등록/판정/은퇴가 생긴 세션에서 이 파일과 프로젝트 지식 사본을 함께 갱신.

## 트랙 공통
- 판정: §11(40거래일 OOS·h20 주지표·부트스트랩 CI·주별일관·Bonferroni) — large만 h60~120(§9).
- 리더보드 정본: leaderboard.py → docs/leaderboard.json (게이트: stage1 부분실행 + 이중실행).
- 트랙 간 IC 절대값 비교 금지. 기각 모델 부활은 새 model_id + 사전등록으로만.

## 현역 (관측·판정 대기)
| 트랙 | 모델 | 스펙 요약 | 등록 | 판정 예정 | 골대 문서 |
|---|---|---|---|---|---|
| v3 | **v30** | 챔피언(과매도 v3). 첫 판정 후 유일 v3 모델. h20 IC '유의' | 20260606 | — (챔피언) | PROJECT_KNOWLEDGE §11 |
| lowvol | **lv_b** | 저변동 트랙 선두·표시 기준(lv_a에서 전환 §27-3) | 20260625 | **~8월 말** | PREREGISTER_lowvol.md |
| lowvol | lv_a·lv_a3·lv_c·lv_d·lv_short·hv_a·sm_a | 저변동 계열 대조군 | 20260625~27 | ~8월 말~9월 초 | PREREGISTER_lowvol.md |
| lowvol | mom_a / mom_b | 모멘텀 대조(표시 별도) / mom_a+눌림목 | 20260627 / 0717 | 9월 초 / 9월 중 | PREREGISTER_mom_b.md |
| wu | wu_a / wu_b | 전체종목 균형형 / 순수선택 대조 | 20260702 | ~9월 초 | PREREGISTER_wu.md |
| wu | **sv_a** | 공매도비중 단독 — 최근 관측 최유력(짝비교 wu_a 대비 CI>0) | 20260715 | ~9월 중 | PREREGISTER_le_sv.md |
| wu | le_a | 저점탈출+OBV+유동성 | 20260715 | ~9월 중 | PREREGISTER_le_sv.md |
| wu | qs_a | 조용한 강자(저변동+52주고+저거래대금) | 20260723 | ~9월 말 | PREREGISTER_qs.md |
| wu | **px_a** | 가격4팩터(lv60+to20+lv20+nh252) — 3년 walk-forward+lv_b 짝비교 근거 | 20260810(첫적재) | **~10월 초** | PREREGISTER_px_a.md |
| large | **ls_t1** | 밸류4팩터 동일가중(ep·bp·rim·dv) 테스트 | 20260806 | h60: 9월~ / h120: 11월~ | PREREGISTER_ls_t1.md |

## 은퇴 (§11 첫 판정 2026-08-09 — 전원 기각, VERDICT_20260809.md)
| 모델 | 사유 요약 |
|---|---|
| v31b·v31d | 유의 악화(Bonferroni CI까지 음수) |
| v31f·v31g | h20 CI 0 걸침 — 채택기준 미달 (f는 h10 재현 '기움' 기록) |
| v31a | BUY 게이트 역효과(차단분 −3.0% > 유지분 −7.0%) |
| v31c | 좋은 저유동성 종목 제외(+6.4%p) → 세트 −2.97%p 유의 악화 |

동결·섀도우 중지(v3_rescore.RETIRED), 스펙·기존 행·아카이브 보존. 수동 재계산: `shadow_run --models`.

## 관측 팩터 레이어 (점수 미반영 — 국면 전환 감시)
stage3: smartmoney·roe·buyback·vol비율·realized_vol 등(§11 E1 수확 대기).
신규 후보(§28 스캔): va_ep(1/PER)·fl_inst20n(기관수급)·sh_credit_rate — 등록은 별도 결정.
데이터 갭: consensus_daily 2일치(적재 점검 필요), valuation_daily 7/6~.
