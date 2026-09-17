# 2026-09-18 — 모델 성적표 페이지(docs/scoreboard.html) 신설 (2026.09.16 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 새 첫 화면 `docs/scoreboard.html`: **"매일 시장별 상위 10을 사서 40거래일 들고 있었다면 시장 평균보다 얼마나 더 벌었나"** 를 전 모델에 같은 규칙으로 잰 표. 한 줄 결론 → 표(40일 수익 · 시장 평균 · 시장보다 더 번 수익 평균/중앙값 · 시장을 이긴 날 · 매수한 날(40일 묶음)) → 행 클릭 시 검증 창·지금 흐름·참고 구간 → 접힘(오늘까지 보유 참고표, 계산 조건).
- 검증 결론 라벨을 쉬운 말로 표시: 유의→**효과 확인됨**, 기움→**좋아 보이지만 확정 아님**, 노이즈→**차이 없음**, 역작동→**반대로 감(점수 높을수록 나쁨)**, 판정 전→**아직 결론 전**. 원래 용어와 확정 날짜를 작은 글씨로 병기(원장 추적용). 운용 중/참고/관측 중 태그는 없앰(은퇴만 표시) — "이게 기준"이라는 오해 방지.
- 모델 이름 = 모델 페이지 링크(filter·lowvol·lva·mom·mom_b·qs·px·sv·_large_test). 트랙 B(대형 ls_t1)는 별도 표.
- 데이터 `docs/scoreboard.json` ← 새 스크립트 `build_scoreboard.py`(읽기 전용·비치명). 배치 `run_all_and_diversify.bat` 에 `build_daily_lists` 뒤 한 줄 추가.
- 진입 링크: `docs/index.html` 카드 "📋 모델 성적표", `docs/leaderboard.html` 상단 안내 배너. 기존 리더보드는 그대로(검증 자료 전체).

## 왜
- 9/17 밤 사용자 결정: 리더보드 첫 화면은 사용자의 실제 매매 방식(상위 10·40일 보유)으로 잰 숫자만, 판정과 관측 분리, 규칙 없는 배지 제거, 쉬운 표현. 코덱스 시안(월별 표)과 Claude 샘플(research/handoff/mock_006_claude_hold40.html)을 거쳐 후자를 채택.
- 같은 모델이 "매일 갈아타기"에서는 1등(lv_a +26%)인데 40일 보유에서는 3위인 식으로 잣대마다 결론이 달라 혼란 → 잣대 하나로 고정.

## 어떻게
| 파일 | 변경 |
|---|---|
| `build_scoreboard.py`(신규) | leaderboard.py 규약(anchor·dedupe·gates)으로 등록일 이후 앵커별 시장 상위10 → t+1 종가 매수·t+41 종가 매도, 같은 시장 전체 평균 대비. iid 참고 구간·최악/최고·오늘까지 보유 참고치. sealed/live 는 registry·leaderboard.json 그대로 옮김 |
| `docs/scoreboard.html`(신규) | 표시 전용, `scoreboard.json?ts` 하나만 fetch, 외부 자원 0, 카드 안 가로 스크롤(휴대폰 깨짐 방지) |
| `run_all_and_diversify.bat` | `python build_scoreboard.py` + FAILED 수집(ASCII, 기존 줄 무변경) |
| `docs/index.html` · `docs/leaderboard.html` | 링크 카드 / 안내 배너 |
| `research/hold40_observe.py` · `research/handoff/mock_006_claude_hold40.html` | 샘플(기록). 운영본은 build_scoreboard.py |
| `research/telegram/POST_20260918_scoreboard.md` + `scoreboard_20260918.png` | 1회성 텔레그램 안내문·캡처(사용자가 직접 게시) |

## 검증(실측)
- 로컬 http.server: 콘솔 오류 0, 트랙 A 12행·트랙 B 1행, 모델 링크 9개 전부 200, 행 클릭 펼침 동작. 9/17 종가 기준 v30 +5.9%p(29일, 이긴 날 93%) · lv_b +1.3%p(16일, 63%) — 9/17 연구 스크립트(hold40_observe) 결과와 동일.
- 점수·판정·게이트 코드 미접촉(leaderboard.py 는 import 만). `python tests/run_tests.py` 통과.

## 한계 / 남은 것
- 이 표는 **참고 성적**: 사전등록 v5 와 뼈대는 같지만 희석 배지 제외·PIT 유니버스·40일 블록 CI 미적용. 정식 결론은 사전등록 절차(2027-06)만.
- ohlcv 미수집 종목(코스닥 글로벌·영문코드, 9/17 기준 stage3 3%·large 10%)은 바구니에서 빠짐(patch 09.15 '전체 점검' 절 참조).
- 리더보드 실시간 라벨(leaderboard.py verdict, IC<−0.03 → 역작동)이 정본 기준(구간)과 어긋나는 문제는 별건으로 보류.

## 추가(00:3x) — 주소 교체
- 사용자 확인: 별도 페이지가 아니라 **기존 리더보드 자리**에 새 화면. → 새 성적표를 `docs/leaderboard.html` 로, 기존 전체 자료는 `docs/leaderboard_full.html` 로 이동(제목 '검증 자료 전체', 상단 배너로 왕복). `scoreboard.html` 은 leaderboard.html 로 자동 이동하는 빈 껍데기. 텔레그램·주간 리캡·각 모델 페이지의 기존 링크(leaderboard.html)는 그대로 새 첫 화면을 연다. 데이터 파일 이름(`scoreboard.json`)과 빌드 스크립트는 그대로.

## 마무리 점검(00:5x, 사용자 요청 "결함·버그 확인")
| 항목 | 결과(실측) |
|---|---|
| 배치 순서 | leaderboard.json 은 run_and_diversify 2.91단계에서 먼저 생성 → Large 단계의 build_scoreboard 가 읽음. 순서 문제 없음 |
| 코드 참조 | notify_telegram·notify_weekly 의 링크는 leaderboard.html(새 첫 화면)로 그대로 유효. run_and_diversify 의 언급은 주석뿐 |
| SEALED 인라인 맵 | 이제 `docs/leaderboard_full.html` 에 있음 — notify_telegram.py 주석 갱신. 판정·은퇴 시 registry + _full 인라인 맵 동기화(종전과 동일, 파일명만 변경) |
| 새 첫 화면 | 데스크톱·375px 모두 콘솔 오류 0, 페이지 가로 넘침 없음(카드 안 스크롤), 트랙 A 12행, 모델 링크 9개 200 |
| 기존 전체 페이지 | leaderboard_full.html 정상 로드(표 10개, meta 26모델), 첫 화면으로 돌아가는 링크 있음. scoreboard.html 은 leaderboard.html 로 자동 이동 확인 |
| 테스트 | 교체 후 `python tests/run_tests.py` 재실행 통과 |

고친 것: `build_scoreboard.py` — 등록 직후 앵커 0개인 모델에서 빈 DataFrame 컬럼 접근으로 전체 실패할 수 있던 경로 방어(컬럼 고정) · 은퇴 모델은 트랙 맨 아래 정렬. 데이터 재생성 결과 수치 동일.

남은 것(별건): leaderboard.py 실시간 라벨 규칙(IC<−0.03 → 역작동, 구간 무시)과 정본 기준 불일치 — _full 페이지 표시만 숫자로 바꾸는 안 대기. ohlcv 미수집 종목(코스닥 글로벌·영문코드) 결정 대기.
