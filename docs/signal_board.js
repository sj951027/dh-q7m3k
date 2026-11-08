// [2026-11-08] 오늘 한 줄 — 모델 × 장세 × 업종 세 등불 (표시 전용). 설계·근거 research/SIGNAL_BOARD_20261108.md §0(규칙은 결과 전 고정)·§1(11년 칸별 숫자).
// 읽는 것: scoreboard.json(regime_money · regime_ad_now · buy_context) · sector_dd.json · paper_account.json(각주 수치). 새 JSON·배치 단계 없음.
// 낱말 원칙: '사라/사지 마라' 없음 — 전부 과거형 사실 + 표본. 어떤 조합도 '안 잃음'으로 읽히게 쓰지 않는다. 점수·판정·게이트·모의 계좌 규칙에 들어가지 않는다.
(function(){
  // §1 E1: 코스피 20일 등락 6칸 × 과매도 대리(20일 수익 하위 20%) 40일 초과(%p, 월 블록 95%) · 11년 신호일 545 · 전 종목 40일(%)과 플러스 비율.
  const E1={A2:{n:15,exc:7.26,lo:2.67,hi:10.72,mkt:15.52,mkt_pos:93},A1:{n:43,exc:1.88,lo:1.18,hi:2.53,mkt:3.87,mkt_pos:70},
            B:{n:181,exc:0.34,lo:-0.14,hi:0.81,mkt:0.36,mkt_pos:54},C:{n:201,exc:-0.25,lo:-0.65,hi:0.13,mkt:-0.26,mkt_pos:55},
            D1:{n:68,exc:-0.99,lo:-1.57,hi:-0.38,mkt:1.15,mkt_pos:65},D2:{n:37,exc:-1.32,lo:-2.2,hi:-0.4,mkt:0.0,mkt_pos:73}};
  const CELL6_LABEL={A2:'가장 많이 빠진 축',A1:'크게 빠진 편',B:'보통 수준의 약세',C:'보통 수준의 강세',D1:'많이 오른 편',D2:'가장 많이 오른 축'};
  const DEEP=-20;   // 업종 '깊음' 구간 — SECTOR_DRAWDOWN_20261108 의 연구 구간값(화면 배지엔 문턱 없음)
  const MIN_N=10;   // 11/6 '자료 적음' 관례(목록 10개 미만)
  const MIN_EVENTS=5; // buy_context.MIN_EVENTS
  const sg=x=>(x>=0?'+':'')+Number(x).toFixed(1);
  const cell6=x=>{if(x==null||isNaN(x)) return null; for(const [k,hi] of [['A2',-10],['A1',-5],['B',0],['C',5],['D1',10]]) if(x<=hi) return k; return 'D2';};

  // ① 모델 등불 (§0-1): 약세·상승 둘 다 n≥10 이고 exc>0 이고 win≥0.5 → 둘 다 / 한쪽만 / 나은 적 없음 / 자료 적음
  function modelLamp(m){
    const rm=m.regime_money||{}, w=rm['약세'], u=rm['상승'];
    const okN=x=>x&&x.n>=MIN_N, good=x=>x.exc_mean>0&&x.win>=0.5;
    const f=x=>x?`${x.n}개 ${sg(x.exc_mean)}%p(${Math.round(x.win*100)}% 나음)`:'—';
    const detail=`약세에 산 날 ${f(w)} · 상승에 산 날 ${f(u)}`;
    if(!(okN(w)&&okN(u))) return {state:'low',word:'자료 적음',detail};
    if(good(w)&&good(u)) return {state:'both',word:'두 장세 모두 시장보다 나았음',detail};
    if(good(w)||good(u)) return {state:'one',word:`${good(w)?'하락장(약세)':'상승장'}에 산 날만 시장보다 나았음`,detail};
    return {state:'none',word:'시장보다 나은 적 없음',detail};
  }
  // ② 장세 등불: (a) buy_context 사건 플러스 비율(기존 규칙 50%·사건 5) (b) E1 칸 CI
  function marketLamp(D){
    const k=D.regime_ad_now&&D.regime_ad_now.kospi; if(!k||k.r20_pct==null) return null;
    const c=cell6(k.r20_pct), parent=c&&(c[0]==='A'?'A':c[0]==='D'?'D':null);
    const bc=D.buy_context&&D.buy_context.kospi; let st=bc&&bc[c], used=c;
    if((!st||st.events_n<MIN_EVENTS)&&parent&&bc&&bc[parent]){st=bc[parent]; used=parent;}
    let a='';
    if(st&&st.events_n>=MIN_EVENTS){const r=st.events_pos/st.events_n;
      a=`${D.buy_context.years||'11년'}간 비슷한 자리 ${st.events_n}번 중 ${st.events_pos}번은 40일 뒤 시장 +(평균 ${sg(st.mean)}%)`+(r<0.5?' → 과거엔 좋은 자리 아니었음':'')+(used!==c?` <span class="sb-m">(${used} 칸 합산)</span>`:'');}
    else a='비슷한 자리 표본 부족(5번 미만)';
    const e=E1[c]; let bState='na', b='';
    if(e){bState=e.lo>0?'win':(e.hi<0?'lose':'na');
      b=`과매도 목록은 ${bState==='win'?'시장을 <b>이기던</b> 자리':bState==='lose'?'시장을 <b>못 이기던</b> 자리':'시장을 이길지 <b>못 가름</b>'} <span class="sb-m">(11년 대리 ${e.n}일 · 시장보다 ${sg(e.exc)}%p [${sg(e.lo)}, ${sg(e.hi)}])</span>`;}
    return {cell:c,label:CELL6_LABEL[c]||'',r20:k.r20_pct,days:k.days,pos10:k.pos10,a,b,bState};
  }
  // ③ 업종: 깊이 빠진 업종 수 — 경고 아님
  function sectorLine(S){
    if(!S||!S.sectors) return '';
    const deep=Object.entries(S.sectors).filter(([,v])=>v&&v.dd20!=null&&v.dd20<=DEEP).sort((x,y)=>x[1].dd20-y[1].dd20);
    const list=deep.map(([k,v])=>`${k} ${v.dd20.toFixed(1)}%`).join(', ');
    return `20일 고점에서 ${Math.abs(DEEP)}% 넘게 빠진 업종 <b>${deep.length}개</b>${deep.length?` (${list})`:''} — <b>피할 근거 없음</b> <span class="sb-m">과거엔 깊이 빠진 업종의 과매도가 오히려 더 좋았음(v30 19개 목록 +6.1%p [+2.3, +9.6] 한 시기 · 10년 대리도 깊을수록 좋음 · 표본 적음). 종목별은 목록의 업종 배지</span>`;
  }
  // 조합 문장표 §0-2 (가중 없음)
  function conclusion(ml,mk){
    if(!mk) return '장세 자료 없음';
    if(ml.state==='low') return `모델 자료 적음 — 장세 줄만 참고`;
    if(ml.state==='both'){
      if(mk.bState==='win') return `모델도 장세도 지금까지 자료로는 좋았던 조합 — 단 <b>'시장보다'</b>이지 '안 잃음'이 아님`;
      if(mk.bState==='lose') return `모델은 좋았지만 이 자리(급등 뒤)에선 과매도가 시장을 못 이겼음 — 쉬어가는 것도 생각 <span class="sb-m">(급등 뒤 신규 0 게이트는 모의 계좌 관측 중 · 효과 미확인)</span>`;
      return `모델은 두 장세 모두 시장보다 나았음 · 이 자리에서 과매도가 시장을 이길지는 못 가름`;
    }
    return `${ml.word} · 장세 줄 병기`;
  }
  function paperNote(P){
    try{const a=P.accounts, last=k=>a[k].nav[a[k].nav.length-1], pct=k=>sg((last(k)[1]-1)*100)+'%';
      const d=last('v30')[0], s=P.start||a.v30.nav[0][0], fd=x=>`${+x.slice(4,6)}/${+x.slice(6,8)}`;
      let t=`시장이 빠지면 같이 빠진다 — 모의 계좌 ${fd(s)}~${fd(d)}: v30 <b>${pct('v30')}</b> · 시장 평균 ${pct('B0_market')}`;
      if(a.v30_gateD0&&a.v30_fixq) t+=` · 급등 뒤 신규 0 ${pct('v30_gateD0')} = 고정 비율 축소 ${pct('v30_fixq')} <span class="sb-m">(차이 없음 → 현금 효과)</span>`;
      return t;}catch(e){return '시장이 빠지면 같이 빠진다';}
  }
  const CSS=`.sb{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:10px 14px;margin:0 0 12px;font-size:13.5px;line-height:1.55;color:#1d2333}
  .sb h2{font-size:15px;margin:0 0 4px}.sb .sb-m{color:#6b7386;font-size:12px}.sb ul{margin:4px 0;padding-left:18px}.sb li{margin:2px 0}
  .sb .sb-tag{display:inline-block;font-size:11.5px;border-radius:5px;padding:0 6px;margin-right:4px;border:1px solid #ccc;color:#555}
  .sb .sb-both,.sb .sb-win{border-color:#9fd3b6;background:#edf8f1;color:#1a6b43}.sb .sb-none,.sb .sb-lose{border-color:#e7b3b0;background:#fdf0ef;color:#9a2f2a}
  .sb .sb-one,.sb .sb-na,.sb .sb-low{border-color:#e0d3a2;background:#fff7dc;color:#8a6d1a}
  .sb .sb-row{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 2px}.sb .sb-cell{flex:1 1 180px;border:1px solid #eef0f5;border-radius:8px;padding:6px 8px}.sb .sb-k{font-weight:600;font-size:12.5px;margin-bottom:3px}
  .sb .sb-cell .sb-tag{font-size:13px;padding:2px 8px;margin:0}
  .sb .sb-con{margin-top:6px;padding:6px 10px;background:#f3f6ff;border-radius:8px;font-size:14px}.sb details{margin-top:4px}.sb summary{cursor:pointer;color:#2f5fd8;font-size:12.5px}
  .sb table{border-collapse:collapse;font-size:12px;margin-top:4px}.sb td,.sb th{padding:2px 8px 2px 0;text-align:left;vertical-align:top}
  @media(max-width:600px){.sb{padding:8px 10px;font-size:13px}.sb ul{padding-left:16px}}`;
  function render(el,D,S,P,model){
    const m=(D.models||[]).find(x=>x.model===model); if(!m) {el.innerHTML=''; return;}
    const ml=modelLamp(m), mk=marketLamp(D);
    const others=(D.models||[]).filter(x=>x.track!=='large'&&!x.retired&&x.model!==model&&x.regime_money).map(x=>{const l=modelLamp(x); return `<tr><td>${x.name}</td><td><span class="sb-tag sb-${l.state}">${l.word}</span></td><td class="sb-m">${l.detail}</td></tr>`;}).join('');
    const asof=D.asof&&D.asof.length===8?`${+D.asof.slice(4,6)}/${+D.asof.slice(6,8)} 종가`:'';
    const mkWord=mk?(mk.bState==='win'?`과매도가 시장을 이기던 자리`:mk.bState==='lose'?`과매도가 시장을 못 이기던 자리`:`과매도가 이길지 못 가름`):'자료 없음';
    const deepN=S&&S.sectors?Object.values(S.sectors).filter(v=>v&&v.dd20!=null&&v.dd20<=DEEP).length:null;
    el.innerHTML=`<style>${CSS}</style><div class="sb"><h2>🚦 오늘 한 줄 <span class="sb-m">· ${asof} · ${m.name} ${m.model} · 전부 지난 기록 — 매수 지시 아님</span></h2>
      <div class="sb-row"><div class="sb-cell"><div class="sb-k">모델</div><span class="sb-tag sb-${ml.state}">${ml.word}</span></div>
        <div class="sb-cell"><div class="sb-k">장세 <span class="sb-m">${mk?`코스피 20일 ${sg(mk.r20)}% · ${mk.label}`:''}</span></div><span class="sb-tag sb-${mk?mk.bState:'na'}">${mkWord}</span></div>
        <div class="sb-cell"><div class="sb-k">업종 <span class="sb-m">${deepN!=null?`깊이 빠진 업종 ${deepN}개`:''}</span></div><span class="sb-tag sb-na">피할 근거 없음</span></div></div>
      <div class="sb-con">→ ${conclusion(ml,mk)}</div>
      <div class="sb-m" style="margin-top:4px">${paperNote(P)}</div>
      <details><summary>숫자·근거 · 다른 모델 · 뜻</summary><ul>
      <li><b>모델</b> ${ml.detail} <span class="sb-m">· 평가 완료 목록 기준, 6~9월 한 시기</span></li>
      ${mk?`<li><b>장세</b> 코스피 20일 ${sg(mk.r20)}% = <b>${mk.label}</b>${mk.days?` ${mk.days}일째`:''} — ${mk.a}<br>${mk.b}</li>`:''}
      <li><b>업종</b> ${sectorLine(S)}</li></ul><table>${others}</table>
      <div class="sb-m" style="margin-top:6px">뜻 — <b>모델</b>: 코스닥 20일선 위/아래로 나눈 상승·약세 장세에 산 목록이 40거래일 뒤 같은 시장 전 종목 평균보다 나았나(둘 다 10개 이상·초과 +·나은 비율 50% 이상이면 "두 장세 모두"). <b>장세</b>: 코스피 20거래일 등락을 여섯 칸으로 나눈 자리에서 11년간 (a) 시장이 40일 뒤 올랐나 (b) 과매도 목록(20일 수익 하위 20% 대리)이 시장을 이겼나 — 구간이 0을 안 걸치면 "이기던/못 이기던", 걸치면 "못 가름". <b>업종</b>: 20일 고점 대비 −20% 이하 업종 수 — 경고가 아니라 사실. 규칙·문턱은 전부 이미 쓰던 값(새로 고른 것 없음) · 근거 research/SIGNAL_BOARD_20261108.md.</div></details></div>`;
  }
  window.SignalBoard={mount:function(sel,opts){opts=opts||{}; const el=typeof sel==='string'?document.querySelector(sel):sel; if(!el) return;
    const q=f=>fetch(f+'?ts='+Date.now()).then(r=>r.ok?r.json():null).catch(()=>null);
    Promise.all([opts.scoreboard?Promise.resolve(opts.scoreboard):q('scoreboard.json'),q('sector_dd.json'),q('paper_account.json')]).then(([D,S,P])=>{try{if(D) render(el,D,S||{},P||{},opts.model||'v30');}catch(e){el.innerHTML='';}});}};
})();
