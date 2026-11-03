"""Post-freeze J10/J06 comparison. Read only; do not import old research script."""
from pathlib import Path
import hashlib,json,sqlite3
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
n=datetime.now(ZoneInfo('Asia/Seoul'))
if n.weekday()<5 and '20:10'<=n.strftime('%H:%M')<'22:30':raise RuntimeError('Batch window')
f=json.loads((OUT/'blind_freeze.json').read_text(encoding='utf-8'))
for name,h in f['files'].items():assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==h
old_path=ROOT/'research/out_slot_gaps/summary.csv'
old=pd.read_csv(old_path).set_index('account')
picks=pd.read_csv(OUT/'picks.csv',dtype=str)
c=sqlite3.connect((ROOT.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True)
c.execute('PRAGMA query_only=ON')
try:
    raw=pd.concat([pd.read_sql_query(f"SELECT ticker,date,is_suspended FROM {t} WHERE date>='20260810'",c)
                   for t in ['daily_ohlcv_extra','daily_ohlcv']],ignore_index=True)
finally:c.close()
raw['ticker']=raw.ticker.astype(str).str.zfill(6)
raw=raw.drop_duplicates(['ticker','date'],keep='last')
susp=set(zip(raw.loc[raw.is_suspended>0,'ticker'],raw.loc[raw.is_suspended>0,'date']))
result={}
for mid in ['v30','lv_b','v32a']:
    led=pd.read_csv(OUT/f'{mid}_cash_ledger.csv',dtype={'ticker':str,'exit_date':str})
    closed=led[led.status=='closed']
    flagged=closed[[((str(t).zfill(6),d) in susp) for t,d in zip(closed.ticker,closed.exit_date)]] if len(closed) else closed
    sizes=picks[(picks.model==mid)&(picks.anchor<'20261030')].groupby('anchor').size()
    result[mid]={'entered':len(led),'closed':len(closed),'closed_on_suspended':len(flagged),
                 'suspended_ret_mean_pct':float(flagged.ret.mean()*100) if len(flagged) else None,
                 'list_min':int(sizes.min()),'short_anchors':int((sizes<20).sum()),'entry_anchors':len(sizes)}
report=ROOT/'research/handoff/REPLY_20261102_j05_replace_vs_cash.md'
snapshot=OUT/'blind_reply.md'
if not snapshot.exists():
    assert hashlib.sha256(report.read_bytes()).hexdigest()==f['blind_reply_sha256']
    snapshot.write_bytes(report.read_bytes())
lines=['## 5. 결과 고정 후 J10·J06 대조','',
       'blind_freeze.json 작성과 검증 뒤 지정 RESEARCH_ops_realism_20261101.md와 paper_slot_gaps_20261031.py를 읽었다. 후자는 실행/import하지 않았으며, 그 파일이 가리키는 기존 out_slot_gaps/summary.csv와 이번 엔진 장부를 대조했다.',
       '지정 운영 메모 본문은 J14·J11·2026 체제에 관한 것이며 J10·J06 수치는 없다. J10·J06 수치는 기존 slot_gaps CSV에서 확인했다.',
       '', '|모델|이번 기본 체결|이번 완결|이번 정지일 예정 청산 J10|목록<20 앵커 J06|목록 최소|이번 대체 J05|',
       '|---|---:|---:|---:|---:|---:|---:|']
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
for mid,x in result.items():
    lines.append(f"|{mid}|{x['entered']}|{x['closed']}|{x['closed_on_suspended']}|{x['short_anchors']}/{x['entry_anchors']}|{x['list_min']}|{summary['models'][mid]['executed_replacements']}|")
lines += ['',
 'J05의 대체는 v30 5건·lv_b 1건으로, J10의 v30 정지일 예정 청산 5건과 절대 건수는 같은 한 자릿수다. 다만 J05는 신규 진입 슬롯, J10은 완결 슬롯을 분모로 하므로 같은 발생률이나 손익 영향이라는 뜻은 아니다. 정지일 청산의 실거래 가능성을 새로 해결하거나 손익을 재계산하지 않았다.',
 f"J06 기존 저장표는 v30 시세표 부재 {int(old.loc['v30','skip_absent'])}건, lv_b {int(old.loc['lv_b','skip_absent'])}건을 담고 있다. 이 표는 현재 본표+보충표 로더와 같지 않은 결과다. 이번에는 기본 체결 v30 {result['v30']['entered']}건·lv_b {result['lv_b']['entered']}건으로 그 누락이 사라졌다. 옛 lv_b 90건을 다음 순위 대체로 해결한 것처럼 합산하지 않는다.",
 '목록 부족에 따른 기존 재분배는 유지했다. lv_b의 시장별 후보가 적은 날에는 11위 후보 자체가 없어 원래 상한가 종목 몫을 현금으로 남겼다. 따라서 J05 결론은 이미 보충표 누락을 고친 현재 기준에서의 추가 효과다.',
 '운영 메모의 J11 미결제 대금 문제는 다른 변수다. 이번에는 요청대로 settle_days=0을 고정했고, T+2 감도나 다른 10개 계좌로 결론을 넓히지 않았다.',
 '', '추가 검증: 저장 NAV에서 수익·최대낙폭·평균현금 재계산 일치. 합성 입력으로 11위 불가 시 12·13위 순차 대체, 15위까지만 허용, 대체 실패 시 목록 길이/현금 몫 유지, 원 목록 무변경을 확인했다(validation.json).',
 '대조 재현: `python -X utf8 -B research/handoff/out_20261102_j05/compare_ops.py`.','']
report.write_text(report.read_text(encoding='utf-8').split('## 5. 결과 고정 후 J10·J06 대조')[0]+'\n'.join(lines),encoding='utf-8')
(OUT/'comparison.json').write_text(json.dumps({'current':result,'old_summary_sha256':hashlib.sha256(old_path.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
