"""Run only after blind_freeze.json. Compare labels, not strategy outcomes."""
from pathlib import Path
import importlib.util
import json
import hashlib
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
code=ROOT/'research/handoff/code_20261102_macro_regime_blind.py'
spec=importlib.util.spec_from_file_location('blind_macro',code)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.guard()
frozen=json.loads((OUT/'blind_freeze.json').read_text(encoding='utf-8'))
assert hashlib.sha256(code.read_bytes()).hexdigest()==frozen['code_sha256']
for name,digest in frozen['files'].items():assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==digest
r=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
own=pd.read_csv(OUT/'events.csv',dtype={'date':str})
flow_path=ROOT/'research/out_flow_regime/events.csv'
flow=pd.read_csv(flow_path,dtype={'date':str})
f=pd.DataFrame({'date':flow.date,'regime':'A','event':True})
f,_=m.macro_axes(f)
table=f[['date','FX20','US20','RATE20']].copy()
table['foreign_C20']=flow.fx20;table['pension_C20']=flow.pen20
rows=[]
for axis in ['FX20','US20','RATE20']:
    table[axis+'_bad']=m.bad_side(table[axis],axis,r['thresholds'][axis])
    for name,col in [('foreign','foreign_C20'),('pension','pension_C20')]:
        b=table[axis+'_bad'];selling=table[col]<=0
        rows.append({'axis':axis,'flow':name,'n':len(table),'macro_bad_flow_sell':int((b&selling).sum()),
                     'macro_bad_flow_buy':int((b&~selling).sum()),'macro_good_flow_sell':int((~b&selling).sum()),
                     'macro_good_flow_buy':int((~b&~selling).sum()),'same_hypothesis_side':int((b==selling).sum())})
table.to_csv(OUT/'flow_comparison.csv',index=False,encoding='utf-8-sig')
comparison={'compared_at':m.guard(),'flow_path':str(flow_path),'flow_sha256':hashlib.sha256(flow_path.read_bytes()).hexdigest(),
            'own_events':len(own),'flow_events':len(flow),'exact_date_overlap':len(set(own.date)&set(flow.date)),
            'thresholds_fixed_from_blind':r['thresholds'],'cross_tabs':rows}
m.dump(OUT/'flow_comparison.json',comparison)
lines=['## 7. 독립 결과 고정 후 수급 연구 대조','',
       '독립 결과를 blind_freeze.json으로 고정한 뒤 지정 수급 연구 본문과 그 문서가 가리킨 out_flow_regime/events.csv를 열었다. 수급 DB나 기존 연구 코드는 열거나 실행하지 않았다.',
       f"이번 A 사건 {len(own)}개와 수급 연구 사건 {len(flow)}개의 정확한 날짜 교집합은 {comparison['exact_date_overlap']}개다. 수급 days.csv는 2015-07-13부터 시작하고 격자 기준도 다르다. 독립 결과를 수급 연구의 22개에 맞춰 재선정하지 않았다.",
       '같은 날의 분류를 비교하려고 수급 연구의 22개 사건 날짜에 거시 축만 다시 조회했다. 이번 눈가림 A 날에서 고정한 중앙값을 그대로 적용했으며, 수급 사건의 결과 수익을 사용해 문턱이나 판정을 바꾸지 않았다.',
       '', '|거시 축|수급 축|거시 나쁨·수급 순매도|거시 나쁨·수급 순매수|거시 좋음·수급 순매도|거시 좋음·수급 순매수|가설상 같은 쪽/22|',
       '|---|---|---:|---:|---:|---:|---:|']
for x in rows:
    lines.append(f"|{x['axis']}|{x['flow']}|{x['macro_bad_flow_sell']}|{x['macro_bad_flow_buy']}|{x['macro_good_flow_sell']}|{x['macro_good_flow_buy']}|{x['same_hypothesis_side']}/22|")
lines += ['', '여기서 수급의 가설상 나쁜 쪽은 C20≤0(순매도), 좋은 쪽은 >0이다. 이는 부호 비교용 정의이며 외국인 추종이 실제로 좋다는 뜻이 아니다. 외국인은 18/22가 순매도이므로 단순 일치율은 불균형에 크게 좌우된다. 연기금도 위 교차표처럼 세 거시 축과 같은 사건을 동일하게 나누지는 않는다.',
          '수급 본문의 외국인 닫음·연기금 보류와 이번 거시 세 축 닫음은 각자의 판정이다. 사건 달력·표본·문턱이 다른 연구의 차이 수치를 직접 빼서 우열이나 추가 예측력을 주장하지 않는다. 이번 대조에는 사건 CSV의 원래 C20 부호를 사용했다.',
          '유가 각주: 2020-04-20의 음수 관측을 포함하는 비교 창 때문에 2020-04-27·2020-05-07·2020-05-14의 OIL20을 제외했다. 세 날짜 모두 A 사건 밖이며 다른 축의 표본은 줄이지 않았다.',
          '', '대조 재현: `python -X utf8 -B research/handoff/out_20261102_macro_regime/compare_flows.py`.',
          '추가 독립 검증: 새 코드와 별도로 SQL 조인으로 4개 날짜 바구니를 재계산해 일치, 567×5=2,835개 축/관측일을 SQL로 전수 대조해 일치, FX 사건 4,000회 부트스트랩을 행 재추출 루프로 재계산해 구간 일치. 계산 결과·코드의 고정 해시도 확인했다.','']
reply=m.REPLY
text=reply.read_text(encoding='utf-8')
snapshot=OUT/'blind_reply.md'
if not snapshot.exists():
    assert hashlib.sha256(reply.read_bytes()).hexdigest()==frozen['blind_reply_sha256']
    snapshot.write_bytes(reply.read_bytes())
prefix=text.split('## 7. 독립 결과 고정 후 수급 연구 대조')[0]
reply.write_text(prefix+'\n'.join(lines),encoding='utf-8')
print(json.dumps(comparison,ensure_ascii=False,indent=2))
