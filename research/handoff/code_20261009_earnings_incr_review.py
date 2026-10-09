"""Offline review tests; fake API and in-memory DB only. Writes named REPLY."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sqlite3
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import earnings_incr as X
sys.stdout.reconfigure(encoding='utf-8')

def guard():
    now=datetime.now(timezone(timedelta(hours=9)))
    if now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
    return now.isoformat(timespec='seconds')

def main():
    started=guard();evidence=[]
    def dbs():
        c=X.open_db(':memory:');o=sqlite3.connect(':memory:')
        o.execute('CREATE TABLE daily_ohlcv(ticker TEXT,date TEXT,close REAL,shares REAL)')
        return c,o
    def filing(name='분기보고서 (2026.03)',date='20260515',rc='20260515000001'):
        return X.parse_filing(dict(corp_cls='Y',stock_code='005930',corp_code='mock',report_nm=name,rcept_dt=date,rcept_no=rc))
    def items(th=200,fr=100,add=700,fradd=600,receipt='20260620000099'):
        return [dict(account_id='dart_OperatingIncomeLoss',sj_div='IS',thstrm_amount=str(th),frmtrm_amount=str(fr),frmtrm_q_amount=str(fr),thstrm_add_amount=str(add),frmtrm_add_amount=str(fradd),rcept_no=receipt)]
    def fake(url,params,key):return dict(status='000',list=items())
    c,o=dbs();f=filing()
    first=X.process(c,o,[f],'mock',fetch=fake)
    o.execute("INSERT INTO daily_ohlcv VALUES('005930','20260514',1000,1000)")
    second=X.process(c,o,[f],'mock',fetch=fake)
    n=c.execute('SELECT count(*) FROM earnings_q').fetchone()[0]
    assert first['no_price']==1 and second['done']==1 and n==0
    evidence.append(f'시세 없음 뒤 시세 보충: 첫 no_price={first["no_price"]}, 다음 done={second["done"]}, earnings_q 행={n} (n=1보고서, 2회 처리).')
    c,o=dbs();o.execute("INSERT INTO daily_ohlcv VALUES('005930','20260319',1000,1000)")
    f=filing('사업보고서 (2025.12)','20260320','20260320000001');available=False
    def fake_y(url,params,key):
        if params['reprt_code']=='11014' and not available:return dict(status='013')
        return dict(status='000',list=items(th=1000 if params['reprt_code']=='11011' else 700,fr=800,add=700,fradd=600))
    first=X.process(c,o,[f],'mock',fetch=fake_y);available=True
    second=X.process(c,o,[f],'mock',fetch=fake_y)
    assert first['no_values']>0 and second['done']==1 and c.execute('SELECT count(*) FROM earnings_q').fetchone()[0]==0
    evidence.append(f'사업보고서 Q3 결손 후 회복: 첫 no_values={first["no_values"]}, 다음 done={second["done"]}, earnings_q 행=0 (n=1보고서, 2회 처리).')
    c,o=dbs();o.execute("INSERT INTO daily_ohlcv VALUES('005930','20260514',1000,1000)")
    f=filing();r=X.process(c,o,[f],'mock',fetch=fake)
    row=c.execute('SELECT rcept_dt,q_op FROM earnings_q').fetchone()
    rc=c.execute("SELECT rcept_no FROM earnings_raw WHERE year=2026").fetchone()[0]
    assert row==('20260515',200.) and rc=='20260515000001'
    evidence.append('API 항목 receipt=20260620000099인데 20260515 원본 처리로 저장: q_op=200, 접수일=20260515, raw 접수번호=20260515000001 (n=1보고서). 항목의 실제 접수번호 검증 없음.')
    parsed=filing('분기보고서 (2026.09)','20261114','20261114000001')
    assert parsed['reprt']=='Q3'
    evidence.append('제목 2026.09 분기보고서는 회사 결산월과 무관하게 Q3로 분류됨 (n=1 가짜 회사). 6월 결산 회사의 9월 1분기를 구별할 입력을 읽지 않음.')
    c=sqlite3.connect('file:'+str((ROOT.parent/'dh-q7m3k-data/earnings.db').resolve())+'?mode=ro',uri=True)
    daily=c.execute("SELECT rcept_dt,count(*) FROM earnings_q WHERE year=2025 AND reprt='Q3' AND rcept_dt BETWEEN '20251101' AND '20251114' GROUP BY rcept_dt ORDER BY rcept_dt").fetchall()
    total=sum(n for _,n in daily);peak=max(n for _,n in daily)
    counts=c.execute('SELECT count(*) FROM earnings_raw').fetchone()[0];last=X.meta_get(c,'last_end');c.close()
    text=f'''# REPLY — 2. earnings_incr 독립 검토

검토 {started}. 결론: 정상 경로 테스트는 통과하지만, 11월 성수기 전 보완이 필요하다. 운영 코드·DB·docs 무수정, DART/KIS 호출 0. 기존 테스트 29개 통과. 추가 검토는 fake 응답과 메모리 DB만 사용했다.

## 가장 중요한 발견 — 실패한 보고서가 처리 완료로 굳음

실측 재현:
'''+'\n'.join('- '+x for x in evidence)+f'''

### [P1] 원자료 저장을 완료 표지로 사용

재현 방법: `code_20261009_earnings_incr_review.py`의 시세 결손·연간 Q3 결손 두 사례(n=2). `ensure_raw`가 원자료를 먼저 저장한 뒤 `no_price`/`no_values` 분기에서 commit하고, 다음 실행은 `raw_rc==f.rcept_no`면 `done`으로 건너뛴다(earnings_incr.py:250,263,274). 원자료의 존재와 최종 earnings_q 저장 성공이 다르다.

영향: 가격 보충·API 회복·의존 보고서 추가 후에도 같은 접수번호는 영구 미반영될 수 있다. 3일 겹침을 늘리는 것만으로 고쳐지지 않는다. 정정 처리 실패도 새 raw 번호만 저장되면 옛 q 값이 남은 채 재시도 중단될 수 있다. 실제 운영에서 몇 건 발생했는지는 확인 못 함.

고치는 안: 접수번호별 상태를 raw_fetched/ready/persisted/needs_retry로 나누거나 최종 저장을 성공했을 때만 완료 표지 저장. 실패 건은 커서와 무관하게 재시도 큐로 유지. 기존 테스트에는 결손이 회복된 뒤의 재처리 검증이 없다.

### [P1] 과거 시점 연구에는 그대로 사용 불가

재현 방법: 원본 11/14 q=1200을 11/20 정정 q=1300으로 갱신해도 접수일 11/14·시총은 유지한다(기존 테스트 n=1). `earnings_q`는 1키 1행이며 `earnings_raw`도 덮어쓴다. 또한 재무 API 요청은 회사/연도/보고서/연결구분으로만 지정하며 접수번호로 원본 버전을 고르지 않는다. 위 fake 응답 접수번호 불일치 사례(n=1)도 그대로 저장된다.

영향: 11/14~19 과거 조회에도 11/20에 알게 된 값이 나타난다. 3일 겹침 목록의 옛 원본을 처리하면서 최신 정정 재무를 받을 수도 있다. `rcept_dt` 고정만으로 그날 알던 값이 보장되지 않는다. 현재 배지 표시에서 원본 접수일부터 만료를 세는 설계와, 과거 재현 자료의 요건을 구분해야 한다.

고치는 안: 최초 값과 버전별 available_at·실제 응답 접수번호를 보존하고 기준시각 이하 버전만 선택. 현재 배지용 표는 별도 사용하되 과거 연구에 그대로 연결하지 말 것. 저장된 최신값으로 실제 과거 버전을 역복원할 수 있는지는 확인 못 함.

### [P2] 12월 결산 확인은 제목의 월만으로 부족

재현 방법: 6월 결산 회사의 '분기보고서 (2026.09)'를 주면 Q3로 통과(n=1 가짜 사례). 사업 12/반기06/분기03·09만 허용해도 같은 월에 보고하는 다른 결산월 회사·결산월 변경의 짧은 사업연도를 가려내지 못한다.

영향: 요청 재무 연도/보고서 코드와 실제 회계 기간이 어긋나거나 다른 기간 값을 받을 수 있다. 실제 해당 기업 수는 확인 못 함. 연결→별도 전환은 quarter_values에서 fs가 다른 의존 보고서와의 혼합을 거부해 결손으로 끝나지만, 같은 fs 문자열이 비교 가능 회계 범위까지 보장하지는 않는다.

고치는 안: 회사 결산월·사업연도 시작/종료일·응답 기간을 확인. 기간/범위 변경은 비교 불가로 분리. 연결·별도별 raw 키를 보존하고 비교 기준을 명시.

### [P2] 조회 커서가 개별 재무 실패를 반영하지 않음

재현 방법: 목록은 정상, 재무 API는 REQUEST_ERROR/013이거나 가격 없음인 경우를 보면 main의 last_end는 list_error가 없다는 이유로 end까지 이동한다(357행). 금융 API 020은 RuntimeError로 커서를 올리지 않고, 목록 오류도 커서를 유지하는 경로는 맞다.

영향: raw를 못 받은 실패는 3일 안이면 재시도되지만, 더 오래 지연되면 조회창 밖으로 사라진다. raw를 받은 실패는 위 P1 때문에 겹침 안에서도 재시도 안 된다. 원본 없는 정정본도 창 밖 원본을 별도로 찾지 않고 제외한다.

고치는 안: 개별 실패 큐·완료 시각을 보관하고 마지막 조회일과 별도로 재시도. 3일 겹침은 늦은 목록에 대한 완충일 뿐 누락 방지 보장이 아니다.

### [P2] --status도 쓰기 연결

재현 방법: main은 --status 분기 전에 open_db를 호출한다(328행). open_db는 sqlite3.connect(path) 후 CREATE/ALTER/commit한다. 이번 검토에서는 CLI --status를 실행하지 않고 `status(mode=ro 연결)`로 같은 정보를 읽었다(n=1 DB).

영향·고치는 안: 상태 확인 명령이 스키마를 바꿀 수 있으므로 읽기 전용 분기를 먼저 선택하도록 한다. 상태 직접 확인: raw n={counts}, last_end={last}. 키·토큰·.env는 읽지 않았다.

## 호출 수와 배치 시간 — 추정과 실측 구분

실측: 보관 earnings_q의 2025-11-01~14 Q3 접수 n={total}행, 최고일 n={peak}행. 이는 보관 성공분만으로 실제 접수 전체/2026 예상치가 아니다. 일별 수: {daily}.

추정 시나리오: 새 Q3 1건당 본 보고서와 두 의존 보고서가 모두 캐시에 없으면 연결만 성공할 때 3회, 연결 실패 후 별도까지면 최대 6회(HTTP 재시도 제외). 최고일 규모 {peak}건을 대입하면 재무 {peak*3:,}~{peak*6:,}회, 목록 약 {(peak+99)//100+1}회 이상(시장 분할·정정·겹침으로 증가 가능). 캐시가 충분하면 본 보고서 1~2회로 낮아진다. 단일 순차 호출·600회/분 간격만으로도 {peak*3/600:.1f}~{peak*6/600:.1f}분이 하한에 가깝고, 평균 응답 0.3초 가정은 {peak*3*.3/60:.1f}~{peak*6*.3/60:.1f}분, 1초 가정은 {peak*3/60:.1f}~{peak*6/60:.1f}분(재시도·목록·기존 다른 단계 미포함). 이 평균 응답시간은 실측이 아닌 가정이다.

실측 비교: 10/8 로그는 정기보고서 n=34·재무/목록 총 호출 n=32·처리 로그 5초. t0가 목록 조회 뒤라 그 5초에 목록 조회 시간은 포함되지 않는다. 이 평시 작은 표본으로 11월 소요시간을 단정할 수 없다. 계정 일일 총한도·다른 프로세스 호출량·2026 실제 접수 집중은 확인 못 함. 속도 상한은 프로세스 안 전 스레드 합산이지 프로세스 사이 계정 전체 일일 예산 공유가 아니다.

## 배지 정의 대조 및 못 한 것

- DROP=−1%, SUE_CAP=0.5, 직전 10달력일 시세, quarter_values 공유는 일치. 연간 Q4는 Y−Q3 누적이고 Q3/같은 fs가 없으면 None이며 **0으로 대체하지 않는다**. 다만 회복 재시도가 막히는 P1이 있다.
- mcap_at은 본 표에서 오래된 값이 하나라도 있으면 더 최근 보충표보다 우선한다. 두 표 중 최신 날짜의 본 표 우선이라는 뜻과 다르다. 실제 중복 종목 영향 수는 확인 못 함. 신호 당일 종가 미래 사용은 없지만, 처음 수집할 때 이미 과거 종가가 수정돼 있으면 접수 당시 실제 가격이라고 보장되지 않는다.
- 미해결 건마다 재현·영향·고치는 안을 위에 적었다. 코드는 변경하지 않았다. 실제 DART 응답·접수 지연·결산월 변경 기업 검증 및 누락 전수 수는 확인 못 함. 사례 수·성공 테스트 수는 기술통계여서 95% 모집단 구간을 붙이지 않았다.
- 기존 테스트 n=29 통과, 추가 독립 재현 n=4 사례. 실행: `python -B tests/test_earnings_incr.py`, `python research/handoff/code_20261009_earnings_incr_review.py`. 후자는 fake API·메모리 DB만 사용. 큰 중간 파일 없음.

2번 검토 완료. 다음 번호: 3번.
'''
    guard();Path(__file__).with_name('REPLY_20261009_earnings_incr_review.md').write_text(text,encoding='utf-8')
    print('DONE',len(evidence),total,peak)
if __name__=='__main__':main()
