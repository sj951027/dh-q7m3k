# [2026.08.3] 2026-08-14~15 — 리더보드 재설계 · 공통 잣대 모의계좌 · lv_a 열람

## 그래서 뭐가 바뀌나
- **leaderboard.html 정보 위계 재설계**: 최상단 요약 카드(🏆 챔피언 상태 + 📅 판정 D-day
  캘린더, 전부 json 파생 자동) → 기본 "간단히 보기"(트랙 그룹·7컬럼·D-day) / "자세히"(기존
  18컬럼) 토글 → 은퇴 v31 계열 기본 접힘 + 🪦 "기각·은퇴" 뱃지(자기 IC '유의' 라벨 오독 방지).
- **💼 공통 잣대 모의계좌 섹션**: 같은 기간·매일 상위20·동일 벤치마크(시장평균 EW·KOSPI)로
  트랙 간 비교 가능한 유일한 표. build_cross_sim.py → docs/cross_sim.json, 파이프라인 2.915
  (2.91 직후, 비치명). 누적수익·시장평균대비bp/일·일변동성·MDD.
- 설명 대폭 보강(쉬운 말): "IC는 낮은데 수익이 높다?"(lv_a vs lv_b — 재는 게 다름), 모의계좌
  용어 8단락(전문용어 제거: EW→시장평균, ENTRY_LAG→전날 선정·다음날 매수 등), MDD=입장료 비유.
- **lva.html 신설**(lv_a 원본 열람): build_lowvol_filter에 --model/--suffix 추가(기본 0-diff),
  2.87c단계, 리더보드 링크. lowvol.html 구성 칩 오기 수정(반전 제외인데 +반전으로 표기돼 있었음).
- 8/13 스케줄러 미발화(전원/조건) → 조건 탭 AC전원 해제·절전 해제 실행·놓친 작업 재실행 설정.

## 왜 바꿨나
- 사용자가 표에서 "지금 뭘 믿고, 다음 판정이 언제고, 실제 시장 대비 어떤지"를 읽기 어려웠음.
  은퇴 모델의 '유의' 라벨과 px_a h1(n=1) 같은 소표본 수치가 오독을 유발.
- 트랙 간 비교 금지 원칙 때문에 "객관적으로 모델을 고를 잣대"가 없다는 답답함 → 잣대를
  통일한 모의계좌로 해소(관측 전용, §11 판정 무관 명시).
- lv_a는 모의계좌 수익이 높게 보이는 국면이 있어 비교 열람 수요 발생 — 단 그 우위가
  7/31 하루(+4.1%p)와 시작일에 좌우되는 노이즈임을 확인(설명에 반영).

## 어떻게
- docs/leaderboard.html(요약카드·캘린더·토글·은퇴접기·crosssim·설명), build_cross_sim.py(신규),
  run_and_diversify.py(2.915), docs/lva.html(신규), build_lowvol_filter.py(--model/--suffix),
  docs/lowvol.html(칩), .gitignore(/latest_*_lva.csv).
- 검증: JS node --check 반복, 실데이터 렌더 시뮬(요약카드·캘린더·모의계좌 12행), cross_sim
  수치를 연구 스크립트와 대조 일치, builder 기본 호출 git diff 0줄(0-diff), lv_a CSV 실생성.
- 관련 연구(research/): lv_ablation(+to20이 3지평 CI>0 — lv_e 후보), lv_blend(혼합 무익·
  lv_a 수익 우위는 창 의존), whole_forward_probe(전체 유니버스 저변동 forward 생존, 반전 사망),
  cross_track_compare(모의계좌 원형), short_credit_scan(공매도비중 강한 기움 — sv_a 재확인).

## 영향 범위
- 판정·점수 0-diff — 전부 표시·관측·연구. 모의계좌는 "관측 전용·판정 무관" 라벨 고정.
- 후속 예약: lv_b 판정 도달(~8/25 저녁) 후 lv_e(저변동+ROE+저회전) 사전등록 — 8/26 알림.
