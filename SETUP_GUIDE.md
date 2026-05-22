# 셋업 가이드 — 30분 안에 끝내기 (Windows)

브라우저만 있으면 됩니다. Git/터미널 설치 불필요.

## 셋업 흐름

1. **레포 생성 & 파일 업로드** (5분)
2. **DART API 키 발급 & 등록** (5분)
3. **GitHub Pages 켜기** (1분)
4. **첫 실행 & 결과 확인** (15분, 대부분 대기)
5. **cron-job.org 자동화 등록** (8분)

준비물: `v2_6_automation.zip`을 PC에서 **압축 해제**해두세요.

---

## 1. 레포 생성 & 파일 업로드 (5분)

1. github.com에서 **New repository**:
   - Name: 원하는 이름 (예: `oversold-screener`)
   - **Private** 선택 ⚠️ 필수
   - **Add a README file** 체크
   - **Create repository**

2. 레포 메인 → **Add file → Upload files**:
   - 압축 푼 폴더의 **`.github` 폴더를 제외한 모든 파일**을 한 번에 드래그
   - 페이지 하단 **Commit changes**

3. `.github/workflows/daily.yml` 만들기 (폴더는 따로 처리해야 함):
   - **Add file → Create new file**
   - 파일명 입력란에 정확히 `.github/workflows/daily.yml` 타이핑
     - 슬래시 입력하면 폴더로 자동 변환됨 (이게 트릭)
   - 압축 푼 폴더에서 `daily.yml`을 **메모장으로 열어** 전체 복사 → 붙여넣기
   - **Commit changes**

4. **확인**: 레포 파일 목록에 .py 파일들 + `.github` 폴더가 다 보이는지

⚠️ `.gitignore`, `.env.example` 같은 점(.)으로 시작하는 파일이 안 올라갔으면 위 3번 방식으로 따로 만드세요.

---

## 2. DART API 키 (5분)

1. https://opendart.fss.or.kr → 우측 상단 **인증키 신청/관리**
2. 가입 (휴대폰 본인인증 필요) → 인증키 신청 → 즉시 발급
3. **인증키 관리**에서 40자 키 복사

GitHub에 등록:

4. 레포 → **Settings** → 좌측 **Secrets and variables → Actions**
5. **New repository secret**:
   - Name: `DART_API_KEY` (정확히 이대로)
   - Secret: 40자 키 붙여넣기
   - **Add secret**

---

## 3. GitHub Pages 켜기 (1분)

1. 레포 → **Settings → Pages**
2. **Source** 드롭다운 → **GitHub Actions** 선택
3. 끝. 저장 버튼 없음

상단에 표시되는 URL(`https://USERNAME.github.io/REPONAME/`) **메모해두세요**. 5단계에서 씁니다.

---

## 4. 첫 실행 & 결과 확인 (15분)

1. 레포 → **Actions** 탭
2. 첫 방문이면 "I understand my workflows..." 버튼 클릭
3. 좌측 **Daily KOSPI/KOSDAQ Screener V2.6** 클릭
4. 우측 **Run workflow → Run workflow** (파란 버튼)
5. 잠시 후 새로고침 → 노란색 실행 표시
6. 클릭해서 진행 상황 보기

**15~25분 후** 모든 단계 ✅ 초록색이면 성공.
이어서 3단계의 GitHub Pages URL 접속 → 대시보드 표시됨.

### 빨간 X가 뜨면

- **1단계 실패**: `DART_API_KEY` Name 오타 또는 키 값 잘못. 2단계 재확인
- **pip 단계 실패**: `requirements.txt` 업로드 누락. 레포 파일 목록 확인
- **그 외**: 빨간 X 단계 클릭 → 에러 메시지 보고 검색

---

## 5. cron-job.org 자동화 (8분)

GitHub의 schedule cron은 30분 이상 지연되므로 외부 트리거를 씁니다.

### 5-A. GitHub PAT 발급 (3분)

1. github.com 우측 상단 프로필 → **Settings**
2. 좌측 맨 아래 → **Developer settings**
3. **Personal access tokens → Fine-grained tokens → Generate new token**
4. 입력:
   - **Token name**: `v2-cron-trigger`
   - **Expiration**: 1년 권장
   - **Repository access**: **Only select repositories** → V2.6 레포 선택
   - **Permissions → Repository permissions** 펼치기:
     - **Actions** = **Read and write** ⭐ 이거 꼭
     - 나머지는 손대지 말기
5. **Generate token** → `github_pat_...`로 시작하는 문자열 **메모장에 복사** (한 번만 보임)

### 5-B. cron-job.org 등록 (5분)

1. https://cron-job.org → **Sign up free** → 가입 → 로그인
2. **CREATE CRONJOB** 클릭

**Common 탭**:
- Title: `V2.6 Daily Run`
- URL: `https://api.github.com/repos/USERNAME/REPONAME/actions/workflows/daily.yml/dispatches`
  - ⚠️ `USERNAME`/`REPONAME`을 본인 것으로 교체

**Schedule 탭**:
- Time zone: `Asia/Seoul`
- Days of week: **Mon~Fri만** (Sat, Sun 해제)
- Hours: **15만** 체크
- Minutes: **40만** 체크

**Advanced 탭**:
- Request method: **POST**
- Request headers — **Add header**로 3개 추가:

  | Name | Value |
  |---|---|
  | `Accept` | `application/vnd.github+json` |
  | `Authorization` | `Bearer 5-A의_PAT` |
  | `X-GitHub-Api-Version` | `2022-11-28` |

  ⚠️ Bearer 다음 한 칸 띄우고 PAT 붙여넣기

- Request body:
  ```
  {"ref":"main"}
  ```

**Notifications 탭** (권장):
- On failure 체크

**CREATE** 클릭

### 5-C. 테스트

1. 작업 목록에서 우측 **▶ Test Run**
2. **HTTP 204** 응답이면 성공
   - 401/403 → PAT 권한 부족 (Actions: Read and write 확인)
   - 404 → URL 오타
3. 1~2분 후 GitHub **Actions** 탭에 새 실행이 떴는지 확인

---

## 완료 후

매일 평일 15:40에 자동 실행. 결과 확인:
- 폰/PC 브라우저로 **3단계의 Pages URL** 접속
- 북마크 추천

## 1년 후 챙길 일

PAT 만료. cron-job.org에서 401 뜨면 새 PAT 발급 → 헤더 Authorization만 교체.

## 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `.github` 폴더가 안 생겨요 | 1-3에서 슬래시(`/`) 포함해 한 번에 타이핑. 이미 잘못 만들었으면 파일 삭제 후 재시도 |
| Pages 접속 시 404 | 3단계 안 했거나, 4단계 첫 실행이 아직 안 끝났음 (Pages 빌드까지 추가 1~2분) |
| cron-job.org 401/403 | 5-A에서 Actions: Read and write 권한 누락 → PAT 재발급 |
| 대시보드 빈 화면 | 4단계 첫 실행이 실패함. Actions 탭 로그 확인 |
