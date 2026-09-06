# MODELS_LEDGER — 전 트랙 모델 원장 (2026-09-04 기준)

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
| lowvol | **lv_b** | 저변동 트랙 선두·표시 기준(lv_a에서 전환 §27-3). **판정 완료 → '기움'** | 20260625 | **판정 2026-08-29** | VERDICT_20260829_lowvol.md |
| lowvol | lv_a | 저변동+ROE+반전(lv_b 대조·lva.html 표시) — **판정 완료 → '노이즈'**, 적재 유지 | 20260625 | 판정 2026-08-29 | VERDICT_20260829_lowvol.md |
| lowvol | sm_a | 초소형 유동성 프리미엄 — **판정 완료 → '노이즈'**(적재 유지·가중 0) | 20260627 | **판정 2026-09-01** | VERDICT_20260901_sm_a.md |
| lowvol | mom_a / mom_b | 모멘텀 대조(표시 별도) / mom_a+눌림목. mom_a 판정 완료 → '노이즈' | 20260627 / 0717 | 판정 완료 / 9월 중 | PREREGISTER_mom_b.md |
| lowvol | **lv_e** | lv_b + to20(저회전) — **등록 완료**(spec_hash 1774127f89ef, 분모 10→11) | **20260901** | 40거래일 ≈ 10월 말 | PREREGISTER_lv_e.md |
| wu | **sv_a** | 공매도비중 단독 — 최근 관측 최유력(짝비교 wu_a 대비 CI>0) | 20260715 | ~9월 중 | PREREGISTER_le_sv.md |
| wu | le_a | 저점탈출+OBV+유동성 | 20260715 | ~9월 중 | PREREGISTER_le_sv.md |
| wu | qs_a | 조용한 강자(저변동+52주고+저거래대금) | 20260723 | ~9월 말 | PREREGISTER_qs.md |
| wu | *sv_b* | *(초안·미등록)* sv_a + crb5(신용잔고) — **sv_a §11 판정 후 등록**(분모 6→7 회피, 8/29 결정) | **미정** | 등록 + 40거래일 | PREREGISTER_sv_b.md |
| v3 | **v30 (2차 창 W2b)** | 8/09 유의가 첫 13앵커(급락→반등)에 의존 → 판정 후 OOS로 재판정. 스펙·분모 불변 | 20260810(창 시작) | **~10/07** | PREREGISTER_v30_w2.md |
| wu | **px_a** | 가격4팩터(lv60+to20+lv20+nh252) — 3년 walk-forward+lv_b 짝비교 근거 | 20260810(첫적재) | **~10월 초** | PREREGISTER_px_a.md |
| large | **ls_t1** | 밸류4팩터 동일가중(ep·bp·rim·dv) 테스트 | 20260806 | h60: 9월~ / h120: 11월~ | PREREGISTER_ls_t1.md |

## 은퇴 (적재·섀도우 중지 — 스펙·spec_hash·기존 행 전부 보존, Bonferroni 분모 불변)
| 트랙 | 모델 | 은퇴일 | 사유 요약 | 정본 |
|---|---|---|---|---|
| v3 | v31b·v31d | 2026-08-09 | 유의 악화(Bonferroni CI까지 음수) | VERDICT_20260809.md |
| v3 | v31f·v31g | 2026-08-09 | h20 CI 0 걸침 — 채택기준 미달 (f는 h10 재현 '기움' 기록) | VERDICT_20260809.md |
| v3 | v31a | 2026-08-09 | BUY 게이트 역효과(차단분 −3.0% > 유지분 −7.0%) | VERDICT_20260809.md |
| v3 | v31c | 2026-08-09 | 좋은 저유동성 종목 제외(+6.4%p) → 세트 −2.97%p 유의 악화 | VERDICT_20260809.md |
| lowvol | lv_c | 2026-09-04 | 역작동(Bonferroni CI까지 음수) | VERDICT_20260829_lowvol.md |
| lowvol | lv_d·hv_a | 2026-09-04 | 역작동 | VERDICT_20260829_lowvol.md |
| lowvol | lv_a3·lv_short | 2026-09-04 | 노이즈 — lv_a 변형(유니버스 상한 60 / 공매도 보조)으로 대조 역할 종료, 표시 미사용 | VERDICT_20260829_lowvol.md |
| wu | wu_a·wu_b | 2026-09-04 | 역작동(유의) 기각 | VERDICT_20260901_wu.md |

- 메커니즘: v3 = v3_rescore.RETIRED(섀도우·동결 중지) · lowvol = lowvol_score.RETIRED · wu = wu_score.RETIRED
  (신규 run 적재만 중지, `--full`/`--run` 재적재도 은퇴 행은 안 지움). 리더보드는 leaderboard.json의
  `retired` 플래그로 '🪦 기각·은퇴' 접힘 표시. 부활은 새 model_id + 사전등록으로만.
- 2026-09-04 은퇴 7개 결정 근거: 판정 완료·현역 대조 역할 종료·표시 미사용(사용자 결정,
  patch_note/20260904_retire7.md). 8/29 '적재 유지' 결정을 뒤집은 것 — 분모는 행 보존으로 그대로(lowvol 11·wu 6).
  wu_a 은퇴로 공통잣대(cross_sim) 주력창·α/β 대표가 wu_a→(제외)/sv_a 로 바뀜(관측 전용).
- 수동 재계산: v3 `shadow_run --models`, lowvol/wu 는 RETIRED 에서 임시 제외 후 실행(원칙상 금지, 연구용만).
- [2026-09-06] 운영 권고 문서 `OPS_GUIDE.md`(강제 없음 — 막는 것은 그 문서 §2만). v30 W2b 재판정 사전등록(위 표).
- [2026-09-06] 정본 판정·은퇴 **표시 단일 소스 = `docs/models_registry.json`**(sealed·retired·money).
  leaderboard.html(SEALED/RET_WHY/RET_DATE)·notify_telegram(SEALED_V2/RETIRED_FALLBACK_V2/MONEY)·notify_weekly(은퇴 제외)가
  읽고, 없으면 각자 인라인 폴백. **판정/은퇴 시 갱신 위치 = 이 원장 + registry 1곳**(종전 4곳 수동). 점수·판정(leaderboard.json) 무관.

## 2차 판정 (lowvol 트랙, 2026-08-29 — VERDICT_20260829_lowvol.md **정본 확정**)
| 모델 | h20 IC | 95% CI | 판정 |
|---|---|---|---|
| **lv_b** | +0.0687 | [−0.0162, +0.1542] | **기움** (채택 아님 — CI 0 걸침) |
| lv_a3 / lv_a / mom_a / lv_short | +0.033 / +0.017 / +0.006 / −0.004 | 전부 0 걸침 | 노이즈 |
| lv_d / hv_a | −0.073 / −0.077 | — | 역작동 |
| lv_c | −0.0962 | [−0.1268, −0.0637] | **역작동(Bonferroni CI까지 음수)** |
| sm_a / mom_b | — | — | 판정 보류(OOS 39 / 27) |

- 짝비교: **lv_b > lv_a는 '우위 기움'**(iid CI<0이나 주블록 감도에서 CI 0 걸침 — VERDICT 각주 ③).
  주블록에서도 생존하는 lv_b 우위는 mom_a·lv_d·lv_c 3건. 본문 CI는 iid 부트스트랩(각주 ③ 명시).
- 확정 처분(8/29): 표시 lv_b 유지·가중 0, 역작동 3종 **적재 유지**(분모 축소 부작용 고려),
  v30 거취는 다른 국면 표본 후 재론. lv_e는 **sm_a 판정 후 등록**.
  → **9/4 갱신: lv_c·lv_d·hv_a·lv_a3·lv_short 은퇴**(적재 중지·행 보존 → 분모 11 그대로). lv_a·sm_a·mom_a 는 적재 유지.
- 각주(필독): 판정 앵커 22개가 전부 20260625~0729 단일 국면 · lv_b 유니버스는 v30의 100%
  부분집합이고 IC 상관 +0.83(주간 +0.91) → v3 판정과 **독립 표본 아님**.

## 3차 판정 (2026-09-01 — VERDICT_20260901_sm_a.md · VERDICT_20260901_wu.md **정본 확정**)
| 트랙 | 모델 | h20 IC | 95% CI | 판정 |
|---|---|---|---|---|
| lowvol | sm_a | +0.0127 | [−0.0711, +0.0990] | 노이즈 (주별 50%, h10·주블록·lv_b 짝비교 전부 0 걸침) |
| wu | wu_a | −0.1079 | [−0.1379, −0.0802] | **역작동(유의) 기각** — Bonferroni(11·6)·주블록까지 전부 음수 |
| wu | wu_b | −0.1309 | [−0.1592, −0.1036] | **역작동(유의) 기각** — 주별 양(+) 0/5주 |

- wu_a−wu_b 짝비교 diff +0.023 CI[−0.019,+0.063] — in-sample wu_a 우위 재현 안 됨.
- 처분(9/1): 셋 다 **적재 유지·가중 0**(분모 행 보존·국면 감시, 8/29 전례). → **9/4 갱신: wu_a·wu_b 은퇴**(적재 중지,
  행 보존). sm_a 는 적재 유지. wu 부활은 새 model_id+사전등록만.
- sm_a 판정 완료로 **lv_e 등록**(20260901, 분모 10→11). sv_a는 판정 전(OOS 32)이나 참고 관측
  IC +0.060 CI 전부 양수·주별 100% — 판정 ~9/10(예약 작업), 조기 등록 없음.

## 관측 팩터 레이어 (점수 미반영 — 국면 전환 감시)
stage3: smartmoney·roe·buyback·vol비율·realized_vol 등(§11 E1 수확 대기).
신규 후보(§28 스캔): va_ep(1/PER)·fl_inst20n(기관수급)·sh_credit_rate — 등록은 별도 결정.
데이터 갭: consensus_daily 2일치(적재 점검 필요), valuation_daily 7/6~.
