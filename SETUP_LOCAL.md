# 로컬 PC 수동 실행 가이드 (Windows)

GitHub 자동화는 그대로 두고, PC에서 **원할 때 수동으로** 실행할 수 있게 합니다.
PC에서 돌린 결과는 PC 폴더에만 남고 GitHub과는 분리됩니다.

## 사용 시나리오

- 자동화가 실패한 날 백업으로 실행
- 시장 시간 외 (예: 점심시간) 시점에 강제로 돌려보기
- 분석을 위해 결과를 엑셀로 자유롭게 가공하고 싶을 때
- 코드 수정 후 즉시 테스트

## 셋업 (1회만, 15분)

### Step 1: 작업 폴더 만들기

1. 원하는 위치에 폴더 생성 (예: `C:\Users\본인이름\Documents\screener`)
2. `v2_6_automation.zip` 압축 해제 → **압축 푼 폴더 안의 파일들을 모두** 위 작업 폴더로 복사
   - `.py`, `.html`, `.md`, `requirements.txt` 등 보이는 파일 + 점(.)으로 시작하는 파일 모두

### Step 2: Python 패키지 설치

1. 작업 폴더에서 주소창 클릭 → 기존 경로 지우고 **`powershell`** 타이핑 → Enter
   - 그 폴더 위치에서 PowerShell이 열림 (편한 방법)
2. PowerShell 창에 입력:
   ```
   pip install -r requirements.txt
   ```
3. 3~5분 정도 패키지 다운로드 진행
4. 마지막에 `Successfully installed ...` 메시지 뜨면 성공

### Step 3: DART API 키 환경변수 설정 (영구)

⚠️ GitHub Secrets에 등록한 것과 별개로 본인 PC에도 키가 있어야 합니다.

PowerShell 창에 (한 줄로):
```powershell
[Environment]::SetEnvironmentVariable("DART_API_KEY", "여기에_본인_DART_키_40자", "User")
```

- 따옴표 안에 본인 DART 키를 정확히 붙여넣기
- 실행해도 아무 메시지 안 뜸 (정상)
- **PowerShell 창을 닫고 새로 열어야** 적용됨

### Step 4: 적용 확인

새 PowerShell 창 열고:
```
echo $env:DART_API_KEY
```
40자 키가 출력되면 OK.

### Step 5: 첫 실행 테스트

작업 폴더에서 PowerShell 열고:
```
python run_all_v2_6.py
```

30~60분 정도 실행됨. 끝나면 폴더에:
- `latest_kospi_final.csv`
- `latest_kosdaq_final.csv`
- 그 외 `archive/`, `snapshots/`, `history.db`, `docs/` 폴더들

이 두 CSV를 더블클릭하면 엑셀에서 열림. 끝!

## 매일 사용하기 — 더블클릭 실행

PowerShell 명령 매번 치기 번거로우니까 **`run_screener.bat`** 파일을 만들어뒀습니다.

1. 작업 폴더에서 `run_screener.bat` 더블클릭
2. 검은 콘솔창이 뜨고 자동으로 파이프라인 실행
3. 끝나면 결과 폴더가 자동으로 열림
4. `latest_*.csv` 더블클릭으로 확인

바탕화면에 바로가기를 만들면 더 편함:
- `run_screener.bat` 우클릭 → **바로 가기 만들기**
- 만들어진 바로가기를 바탕화면으로 끌어다 놓기
- 바탕화면에서 **더블클릭** → 끝

## 결과 파일 위치

작업 폴더 안:
- `latest_kospi_final.csv` — 코스피 최신 결과 (매 실행마다 덮어쓰기)
- `latest_kosdaq_final.csv` — 코스닥 최신 결과
- `archive/YYYYMMDD/kospi/` — 그날 raw CSV (참고용)
- `history.db` — 모든 시점 데이터 (SQLite)
- `docs/index.html` — 로컬 대시보드 (브라우저로 열기 가능)

## 주의사항 — GitHub 자동화와 분리

- 본인 PC에서 돌린 결과는 **GitHub에 자동 업로드되지 않습니다**.
- 클라우드 대시보드(`https://sj951027.github.io/dh-q7m3k/`)는 여전히 GitHub Actions가 업데이트.
- 로컬과 클라우드는 별개 데이터셋. 헷갈리지 않게 주의.
- 만약 로컬 결과도 GitHub에 푸시하고 싶어지면 B안(Git 셋업)으로 진행.

## 트러블슈팅

| 증상 | 해결 |
|---|---|
| `pip 명령을 찾을 수 없음` | Python 재설치 시 "Add Python to PATH" 체크 |
| `DART_API_KEY가 입력되지 않았습니다` | Step 3 다시 + PowerShell 새 창으로 열기 |
| 한글이 깨져 보임 | `latest_*.csv`를 엑셀로 열 때 "데이터 가져오기 → CSV"로 UTF-8 선택 |
| 실행 도중 PC 절전모드 진입 | 윈도우 설정 → 전원 → 절전 안 함 |
| FinanceDataReader 에러 | `pip install --upgrade finance-datareader` |
| pip install이 너무 느림 | `pip install -r requirements.txt --user` 시도 |
