# V2.6 자동화 셋업 가이드 — KOSPI + KOSDAQ + 대시보드

매일 장 마감 후 KOSPI/KOSDAQ 과매도 스크리너를 자동 실행하고,
결과를 SQLite + Parquet으로 누적하고,
GitHub Pages에 대시보드를 자동 배포합니다.

## 전체 구조

```
스케줄러 (GitHub Actions, 평일 KST 15:40)
   ↓
파이프라인 (run_all_v2_6.py)
   ├─ KOSPI:  Stage 1 → Stage 2 → Stage 3
   └─ KOSDAQ: Stage 1 → Stage 2 → Stage 3 (가중치 재튜닝됨)
   ↓
누적 적재 (accumulate_history.py)
   ├─ history.db                          (SQLite, market 컬럼으로 구분)
   └─ snapshots/YYYYMMDD/*.parquet        (일별 압축 스냅샷)
   ↓
대시보드 (build_dashboard.py)
   └─ docs/index.html                     (GitHub Pages 자동 서빙)
   ↓
URL 한 줄로 확인 → https://USERNAME.github.io/REPONAME/
```

## 코스닥 vs 코스피 — 가중치 재튜닝 내역

코스닥은 변동성/외인 비중/수출주 비중이 코스피와 달라 별도 튜닝이 필요합니다.

| 항목 | KOSPI | KOSDAQ |
|---|---|---|
| 시장 universe | `fdr.StockListing('KOSPI')` | `fdr.StockListing('KOSDAQ')` |
| 시장 지수 (레짐 판단) | KS11 | KQ11 |
| 약세장 페널티 | -10 | **-7** (변동성 큼) |
| 반등장 페널티 | -5 | **-3** |
| 환율 영향 최대 | -3 | **-1** (수출주 적음) |
| 외인 수급 페널티 | -3 ~ +2 | **-2 ~ +1** (외인 비중 작음) |
| 외인 임계값 (5일 누적) | ±2000~5000억 | **±1000~2500억** |
| 시총 상위 proxy 종목 | 삼전, SK하닉 등 | 에코프로비엠, 셀트리온헬스 등 |
| 과매도 최소점수 | 50 | **45** (등락 폭 큼) |
| 스팩(SPAC) 제외 | — | **추가** |

## 셋업 절차

### 1단계: GitHub 레포 생성 (Private 권장)

1. github.com에서 **New repository** → **Private** 선택
2. 로컬에서 클론하고 V2.6 파일 전체 복사 → push

### 2단계: DART API 키를 Secrets에 등록

⚠️ **기존에 코드에 박혀있던 키는 노출됐으니 OpenDART에서 새로 발급받으세요.**

1. https://opendart.fss.or.kr/ → 인증키 신청 (무료, 5분)
2. 레포 → **Settings → Secrets and variables → Actions → New repository secret**
3. Name: `DART_API_KEY`, Value: 새로 발급받은 키

### 3단계: GitHub Pages 활성화

1. 레포 → **Settings → Pages**
2. **Build and deployment** → Source: **GitHub Actions** 선택
3. 첫 워크플로우 실행 후 `https://USERNAME.github.io/REPONAME/` 에서 접근 가능

### 4단계: 로컬 테스트 (선택)

```bash
pip install -r requirements.txt
export DART_API_KEY="새로_발급받은_키"   # Mac/Linux
# $env:DART_API_KEY="..."                # Windows PowerShell

# 전체 (코스피 + 코스닥)
python run_all_v2_6.py

# 한 시장만
python run_all_v2_6.py --market kosdaq

# 대시보드만 다시 생성 (DB는 그대로)
python build_dashboard.py
# 생성된 docs/index.html을 브라우저로 열면 확인 가능
```

### 5단계: 외부 스케줄러 (cron-job.org) — **시간 지연 없이 정확히 실행**

GitHub Actions의 `schedule:` cron은 무료 티어에서 **5~30분, 피크엔 1시간 이상** 지연될 수 있습니다.
장 마감 후 신선한 데이터를 받아야 하므로, **cron-job.org가 정해진 시간에 GitHub API를 직접 호출**해서 워크플로우를 트리거하는 방식을 씁니다. 다른 검증된 한국 주식 자동화 프로젝트에서도 같은 패턴을 씁니다.

지연 비교:
| 방식 | 평일 15:40 트리거 시 실제 실행 |
|---|---|
| GitHub Actions `schedule:` cron | 15:45 ~ 16:10 (지연 변동 큼) |
| cron-job.org → workflow_dispatch | **15:40:05 ~ 15:40:15 (거의 정확)** |

#### 5-1. GitHub Personal Access Token (PAT) 발급

cron-job.org가 GitHub API를 호출하려면 인증 토큰이 필요합니다.

1. github.com → 오른쪽 위 프로필 → **Settings**
2. 맨 아래 **Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
3. 설정:
   - **Token name**: `v2-cron-trigger` (아무 이름)
   - **Expiration**: 1년 (만료 후 갱신 필요)
   - **Repository access**: Only select repositories → 해당 V2.6 레포만 선택
   - **Repository permissions** → **Actions**: **Read and write**
   - **Repository permissions** → **Metadata**: Read-only (자동 선택됨)
4. **Generate token** → 생성된 토큰(`github_pat_...`)을 메모장 등에 임시 저장 (한 번만 표시됨)

#### 5-2. cron-job.org 등록

1. https://cron-job.org → **Sign up free** → 가입 후 로그인
2. 대시보드 → **CREATE CRONJOB**
3. **Common** 탭:
   - **Title**: `V2.6 Daily Run`
   - **URL**: `https://api.github.com/repos/USERNAME/REPONAME/actions/workflows/daily.yml/dispatches`
     - `USERNAME`과 `REPONAME`을 실제 값으로 교체
4. **Schedule** 탭:
   - **Time zone**: `Asia/Seoul`
   - **Schedule**:
     - Days of week: **Mon ~ Fri** (월~금만 체크)
     - Hours: **15**
     - Minutes: **40**
     - 나머지(일, 월, 요일)는 every로 둠
5. **Advanced** 탭:
   - **Request method**: **POST**
   - **Request headers**:
     ```
     Accept: application/vnd.github+json
     Authorization: Bearer github_pat_여기에_5-1에서_받은_토큰
     X-GitHub-Api-Version: 2022-11-28
     ```
   - **Request body** (POST 데이터):
     ```json
     {"ref":"main"}
     ```
     (브랜치명이 `master`라면 `main` 대신 `master`)
6. **Notifications** 탭 (선택): 실패 시 이메일 알림 받기 체크
7. **CREATE** → 목록에 등록됨

#### 5-3. 동작 확인

- 등록 후 cron-job.org의 작업 목록에서 **TEST RUN** 버튼 → 즉시 실행됨
- 응답 코드가 **204** (No Content)면 성공 — GitHub API는 트리거 받은 즉시 204만 돌려주고 워크플로우는 백그라운드에서 시작
- 1~2분 뒤 GitHub 레포 → **Actions** 탭에서 새 실행이 떴는지 확인

#### 5-4. (선택) 다른 시간대도 추가하고 싶다면

cron-job.org에서 **CREATE CRONJOB**을 또 만들면 됩니다. URL과 헤더는 동일하고 시간만 다르게:
- 08:30 아침 점검용 / 19:00 야간 재실행 등

### 6단계: 첫 워크플로우 실행 (수동 테스트)

```bash
git add .
git commit -m "Setup V2.6 KOSPI+KOSDAQ automation"
git push
```

- 레포 → **Actions** 탭 → **Daily KOSPI/KOSDAQ Screener V2.6** 클릭 → **Run workflow** 로 즉시 테스트
- 첫 실행이 성공하면 5-3의 cron-job.org TEST RUN으로 한 번 더 확인
- 다음 평일 KST 15:40에 자동 실행 시작

## 데이터 활용 예시

### SQL로 직접 분석
```python
import sqlite3, pandas as pd
conn = sqlite3.connect("history.db")

# 코스닥에서 지난달 평균 점수 상위 종목
df = pd.read_sql("""
  SELECT name, ticker,
         AVG(final_score) AS avg_score,
         COUNT(*) AS appearances
  FROM stage3_final
  WHERE market='kosdaq' AND run_id >= '20260401'
  GROUP BY ticker, name
  HAVING appearances >= 5
  ORDER BY avg_score DESC LIMIT 30
""", conn)

# 코스피 vs 코스닥 단골 비교
df = pd.read_sql("""
  SELECT market, COUNT(DISTINCT ticker) AS unique_stocks,
         AVG(final_score) AS avg_score
  FROM stage3_final
  WHERE run_id >= '20260401'
  GROUP BY market
""", conn)
```

### Parquet 스냅샷 직접 읽기
```python
df_kospi  = pd.read_parquet("snapshots/20260522/kospi_stage3.parquet")
df_kosdaq = pd.read_parquet("snapshots/20260522/kosdaq_stage3.parquet")
```

## 주의사항

- **공휴일**: 한국 휴장일에도 cron이 돌지만 데이터 소스가 빈 결과를 주면 자동으로 종료. DB는 그날 비어있게 됨 (정상).
- **GitHub Actions 무료 한도**: Private 레포 월 2,000분 무료. 코스피+코스닥 둘 다 돌려도 1회 15~25분 예상이라 월 22거래일 × 25분 = 550분으로 여유.
- **DART 레이트리밋**: 분당 호출 제한이 있어 코스피→코스닥 순차 실행 사이 약간의 텀을 두면 안전. 현재 코드는 안전한 sleep이 포함됨.
- **history.db 크기**: 거래일당 약 200KB~1MB 증가 (양 시장). 1년이면 ~200MB. 그 이상 커지면 오래된 데이터를 export 후 DB 정리 또는 Git LFS 고려.
- **첫 며칠은 단골 종목 섹션이 비어있음**: 누적 데이터가 쌓이려면 2회 이상 필요.

## 코스닥 가중치는 어떻게 검증/조정하나요?

본 튜닝은 일반적 시장 특성에 근거한 합리적 추정입니다. 한 달 정도 누적한 뒤:
```python
# 코스피 vs 코스닥 결과 통계 비교
df = pd.read_sql("""
  SELECT market, market_regime, COUNT(*) AS n,
         AVG(stage1_count) AS avg_oversold
  FROM runs GROUP BY market, market_regime
""", conn)
```
- 코스닥에서 약세장 빈도가 너무 높다면 페널티를 한 단계 더 완화 (-7 → -5)
- 코스닥에서 과매도 종목 수가 코스피의 2배 이상이면 MIN_SCORE 상향 (45 → 48)
- 외인 수급이 0에 가깝게만 나오면 임계값 더 축소

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `DART_API_KEY가 입력되지 않았습니다` | 환경변수 미설정 | Secrets 또는 export 확인 |
| 코스닥 1단계가 universe 0개로 종료 | FDR이 KOSDAQ 리스팅 못 가져옴 | 다음날 재시도, FDR 업데이트 |
| GitHub Pages 404 | Pages 활성화 안 됨 | Settings → Pages → Source: GitHub Actions |
| 대시보드가 빈 화면 | DB에 데이터 없음 | 파이프라인이 한 번이라도 성공했는지 확인 |
| cron-job.org TEST RUN이 401/403 | PAT 만료 또는 권한 부족 | PAT 재발급, **Actions: Read and write** 권한 확인 |
| cron-job.org TEST RUN이 404 | URL 오타 | `repos/USERNAME/REPONAME/actions/workflows/daily.yml/dispatches` 정확히 확인 |
| cron-job.org 204 성공인데 Actions 실행 안 됨 | body의 `ref` 브랜치명 오류 | 기본 브랜치명(`main` vs `master`) 확인 |
| GitHub Actions가 새벽에 멋대로 실행 | schedule cron이 살아있음 | `daily.yml`의 `schedule:` 부분이 주석 처리됐는지 확인 |
| 코스닥 단골 종목이 전부 스팩 | (이제 자동 제외됨) | — |
