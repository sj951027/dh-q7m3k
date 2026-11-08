// [2026-11-08] 오늘 한 줄 — 모델 × 장세 × 업종 세 등불 (표시 전용). 설계·근거 research/SIGNAL_BOARD_20261108.md §0(규칙은 결과 전 고정)·§1(11년 칸별 숫자)·§5(Codex 검토 뒤 문구 개정 11/8 저녁).
// 읽는 것: scoreboard.json(regime_money · regime_ad_now · buy_context · fix) · sector_dd.json · paper_account.json(각주 수치). 새 JSON·배치 단계 없음.
// 낱말 원칙: '사라/사지 마라' 없음 — 전부 과거형 사실 + 대상·기간·표본. 세 줄은 따로 잰 기록이며 조합을 함께 시험한 결과가 아니다(§5). 어떤 조합도 '안 잃음'으로 읽히게 쓰지 않는다. 점수·판정·게이트·모의 계좌 규칙에 들어가지 않는다.
(function(){
  // §1 E1: 코스피 20일 등락 6칸 × 과매도 대리(20일 수익 하위 20%) 40일 초과(%p, 월 블록 95%) · 11년 신호일 545 · 전 종목 40일(%)과 플러스 비율. Codex 독립 재계산 일치(11/8).
  const E1={A2:{n:15,mo:11,exc:7.26,lo:2.67,hi:10.72,mkt:15.52,mkt_pos:93},A1:{n:43,mo:27,exc:1.88,lo:1.18,hi:2.53,mkt:3.87,mkt_pos:70},
            B:{n:181,mo:90,exc:0.34,lo:-0.14,hi:0.81,mkt:0.36,mkt_pos:54},C:{n:201,mo:100,exc:-0.25,lo:-0.65,hi:0.13,mkt:-0.26,mkt_pos:55},
            D1:{n:68,mo:48,exc:-0.99,lo:-1.57,hi:-0.38,mkt:1.15,mkt_pos:65},D2:{n:37,mo:18,exc:-1.32,lo:-2.2,hi:-0.4,mkt:0.0,mkt_pos:73}};
  const CELL6_LABEL={A2:'가장 많이 빠진 축',A1:'크게 빠진 편',B:'보통 수준의 약세',C:'보통 수준의 강세',D1:'많이 오른 편',D2:'가장 많이 오른 축'};
  const DEEP=-20;   // 업종 '깊음' 구간 — SECTOR_DRAWDOWN_20261108 의 연구 구간값(화면 배지엔 문턱 없음)
  const MIN_N=10;   // 11/6 '자료 적음' 관례(목록 10개 미만) — 구간별. 전체는 첫 표와 같은 lowN(fix.n<10 또는 blocks<1)을 먼저 적용
  const MIN_EVENTS=5; // buy_context.MIN_EVENTS
  const fin=x=>typeof x==='number'&&isFinite(x);
  const sg=x=>(x>=0?'+':'')+Number(x).toFixed(1);
  const fd=x=>x&&x.length===8?`${+x.slice(4,6)}/${+x.slice(6,8)}`:'';
  const cell6=x=>{if(x==null||isNaN(x)) return null; for(const [k,hi] of [['A2',-10],['A1',-5],['B',0],['C',5],['D1',10]]) if(x<=hi) return k; return 'D2';};

  // ① 모델 등불 (§0-1 + §5 개정): 전체 자료 적음(첫 표 규칙) → 구간별 n≥10 → 두 조건(평균 초과 > 0 · 우위 비율 ≥ 50%) 충족 구간 수로 다섯 상태
  function modelLamp(m){
    const rm=m.regime_money||{}, w=rm['약세'], u=rm['상승'], fx=m.fix||{};
    const okN=x=>x&&fin(x.n)&&x.n>=MIN_N, has=x=>x&&fin(x.exc_mean)&&fin(x.win), good=x=>has(x)&&x.exc_mean>0&&x.win>=0.5;
    const f=x=>x&&fin(x.n)?(has(x)?`${x.n}개 ${sg(x.exc_mean)}%p(${Math.round(x.win*100)}% 우위)`:`${x.n}개 값 없음`):'—';
    const per=(w&&u)?` · 추천일 ${fd([w.first,u.first].filter(Boolean).sort()[0])}~${fd([w.last,u.last].filter(Boolean).sort().slice(-1)[0])}`:'';
    const detail=`약세에 산 목록 ${f(w)} · 상승에 산 목록 ${f(u)}${per}`;
    if(!fin(fx.n)||fx.n<MIN_N||(fx.blocks!=null&&fx.blocks<1)) return {state:'low',word:'자료 적음',detail};
    if(!(okN(w)&&okN(u))) return {state:'low',word:'자료 적음',detail};
    if(!(has(w)&&has(u))) return {state:'low',word:'자료 없음',detail:'모델 기록을 표시할 수 없음 · '+detail};
    if(good(w)&&good(u)) return {state:'both',word:'두 구간 모두 평균 초과 + · 절반 이상 우위',detail};
    if(good(w)||good(u)) return {state:'one',word:`${good(w)?'약세':'상승'} 구간만 두 조건 충족`,detail};
    if(w.exc_mean<=0&&u.exc_mean<=0) return {state:'none',word:'두 구간 모두 평균 초과가 0 이하였음',detail};
    return {state:'mixed',word:'평균 초과와 우위 비율이 엇갈림',detail};
  }
  // ② 장세 등불(코스피 기준): (a) buy_context 사건 플러스 비율(기존 규칙 50%·사건 5) (b) E1 칸 CI. 코스닥만 급락이면 주의 문장(§5 4-4)
  function marketLamp(D){
    const k=D.regime_ad_now&&D.regime_ad_now.kospi; if(!k||!fin(k.r20_pct)) return null;
    const q=D.regime_ad_now&&D.regime_ad_now.kosdaq;
    const c=cell6(k.r20_pct), parent=c&&(c[0]==='A'?'A':c[0]==='D'?'D':null);
    const bc=D.buy_context&&D.buy_context.kospi; let st=bc&&bc[c], used=c;
    if((!st||st.events_n<MIN_EVENTS)&&parent&&bc&&bc[parent]){st=bc[parent]; used=parent;}
    let a='';
    if(st&&st.events_n>=MIN_EVENTS){const r=st.events_pos/st.events_n;
      a=`${D.buy_context.years||'11년'}간 비슷한 자리 ${st.events_n}번 중 ${st.events_pos}번은 40일 뒤 시장 +(평균 ${sg(st.mean)}%)`+(r<0.5?' → 과거엔 오른 자리가 적었음':'')+(used!==c?` <span class="sb-m">(${used} 칸 합산)</span>`:'');}
    else a='비슷한 자리 표본 부족(5번 미만)';
    const e=E1[c]; let bState='na', b='';
    if(e){bState=e.lo>0?'win':(e.hi<0?'lose':'na');
      b=`과거 유사 칸에서 대리 과매도의 40일 평균은 시장보다 ${bState==='win'?'<b>높았음</b>':bState==='lose'?'<b>낮았음</b>':'<b>차이를 못 가림</b>'} <span class="sb-m">(${sg(e.exc)}%p [95% ${sg(e.lo)}, ${sg(e.hi)}] · ${e.n}신호일·${e.mo}개월 · 11년 대리)</span>`;}
    const kqOnly=q&&fin(q.r20_pct)&&q.r20_pct<=-5&&!(k.r20_pct<=-5);
    const kq=q&&fin(q.r20_pct)?`코스닥 20일 ${sg(q.r20_pct)}%${kqOnly?' — <b>코스닥만 급락한 상황: 아래 코스피 기록만으로 지금을 판단하기 어려움</b>':''}`:'';
    return {cell:c,label:CELL6_LABEL[c]||'',r20:k.r20_pct,days:k.days,pos10:k.pos10,a,b,bState,kq,kqOnly};
  }
  // ③ 업종: 집계 가능한 업종 중 20일 고점 대비 −20% 이하 업종 수 — 전체 업종 지도 기준(선택 목록 안 종목 수가 아님) · 경고 아님
  function sectorInfo(S){
    if(!S||!S.sectors) return null;
    const all=Object.entries(S.sectors).filter(([,v])=>v&&fin(v.dd20));
    const deep=all.filter(([,v])=>v.dd20<=DEEP).sort((x,y)=>x[1].dd20-y[1].dd20);
    return {total:all.length,deep,asof:S.asof||'',list:deep.map(([k,v])=>`${k} ${v.dd20.toFixed(1)}%`).join(', ')};
  }
  function sectorLine(si){
    if(!si) return '업종 자료 없음(sector_dd.json 을 읽지 못함) — 연구 결론과 별개';
    return `집계 가능한 ${si.total}업종 중 20일 고점 대비 ${DEEP}% 이하 <b>${si.deep.length}개</b>${si.deep.length?` (${si.list})`:''}${si.asof?` <span class="sb-m">· 기준 ${fd(String(si.asof))}</span>`:''} — 이번 과매도 연구에서는 <b>업종 하락만으로 종목을 제외할 근거를 확인하지 못했음</b> <span class="sb-m">(v30 깊은 업종 19목록 +6.1%p [+2.3, +9.6] 한 시기 · 경고 검정 +2.96 [−1.16, +6.79] · 표본 적음 — 안전함·저점임의 근거는 아님). 종목별은 목록의 업종 배지</span>`;
  }
  // 결론 줄(§5 개정): 두 기록을 나란히 — 함께 시험한 결과가 아님을 항상 밝힘
  function conclusion(ml,mk){
    if(!mk) return '장세 자료 없음';
    if(ml.state==='low') return `모델 자료 적음 — 장세 줄만 참고`;
    const tail=` <span class="sb-m">(두 기록은 따로 잰 것 — 이 조합을 함께 시험한 결과는 아님)</span>`;
    if(ml.state==='both'){
      if(mk.bState==='win') return `모델 기록(한 시기)도 이 칸의 과거 대리 과매도 기록도 시장보다 나았음 — 단 <b>시장보다 나았어도 손실일 수 있음</b>`+tail;
      if(mk.bState==='lose') return `모델 기록은 좋았으나 과거 이 칸에서는 대리 과매도 평균이 시장보다 낮았음 <span class="sb-m">(매수 중단의 계좌 개선 효과는 별도 관측 중 · 효과 미확인)</span>`+tail;
      return `모델 기록은 두 구간 모두 좋았음 · 이 칸에서 과매도가 시장을 이길지는 못 가름`+tail;
    }
    return `${ml.word} · 장세 줄 병기`+tail;
  }
  // 손실 각주(§5 4-5): 고정 등호·인과 결론 없이 수치와 날짜만
  function paperNote(P){
    try{const a=P.accounts, last=k=>a[k].nav[a[k].nav.length-1], v=k=>(last(k)[1]-1)*100, pct=k=>sg(v(k))+'%';
      const d=last('v30')[0], s=P.start||a.v30.nav[0][0];
      const head=v('v30')<0?`<b>손실도 있었음</b> — 모의 계좌 ${fd(s)}~${fd(d)}: v30 <b>${pct('v30')}</b> · 시장 평균 ${pct('B0_market')}${v('v30')>v('B0_market')?' (덜 잃었지만 손실이었음)':''}`
                               :`시장보다 나았어도 손실일 수 있음 — 모의 계좌 ${fd(s)}~${fd(d)}: v30 <b>${pct('v30')}</b> · 시장 평균 ${pct('B0_market')}`;
      let gate='';
      if(a.v30_gateD0&&a.v30_fixq){const g=v('v30_gateD0'), f=v('v30_fixq'), same=g.toFixed(1)===f.toFixed(1);
        gate=`${fd(d)} 기준 급등 뒤 신규 0 계좌 ${sg(g)}% · 고정 비율 축소 계좌 ${sg(f)}% — ${same?'소수 첫째 자리에서 같았음':`차이 ${sg(g-f)}%p`}. 이 비교만으로 장세를 가리는 효과는 확인되지 않았음(관측 중).`;}
      return {head,gate};}catch(e){return {head:'시장보다 나았어도 손실일 수 있음',gate:''};}
  }
  const CSS=`.sb{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:10px 14px;margin:0 0 12px;font-size:13.5px;line-height:1.55;color:#1d2333}
  .sb h2{font-size:15px;margin:0 0 4px}.sb .sb-m{color:#6b7386;font-size:12px}.sb ul{margin:4px 0;padding-left:18px}.sb li{margin:2px 0}
  .sb .sb-tag{display:inline-block;font-size:11.5px;border-radius:5px;padding:0 6px;margin-right:4px;border:1px solid #ccc;color:#555}
  .sb .sb-both,.sb .sb-win{border-color:#9fd3b6;background:#edf8f1;color:#1a6b43}.sb .sb-none,.sb .sb-lose{border-color:#e7b3b0;background:#fdf0ef;color:#9a2f2a}
  .sb .sb-one,.sb .sb-na,.sb .sb-low,.sb .sb-mixed{border-color:#e0d3a2;background:#fff7dc;color:#8a6d1a}
  .sb .sb-row{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 2px}.sb .sb-cell{flex:1 1 180px;border:1px solid #eef0f5;border-radius:8px;padding:6px 8px}.sb .sb-k{font-weight:600;font-size:12.5px;margin-bottom:3px}
  .sb .sb-cell .sb-tag{font-size:13px;padding:2px 8px;margin:0}.sb .sb-s{display:block;font-size:11.5px;color:#6b7386;margin-top:3px}
  .sb .sb-con{margin-top:6px;padding:6px 10px;background:#f3f6ff;border-radius:8px;font-size:13.5px}.sb details{margin-top:4px}.sb summary{cursor:pointer;color:#2f5fd8;font-size:12.5px}
  .sb table{border-collapse:collapse;font-size:12px;margin-top:4px}.sb td,.sb th{padding:2px 8px 2px 0;text-align:left;vertical-align:top}
  @media(max-width:600px){.sb{padding:8px 10px;font-size:13px}.sb ul{padding-left:16px}.sb .sb-con{font-size:13px;padding:5px 8px}.sb .sb-con .sb-m{display:none}
  .sb .sb-row{gap:6px}.sb .sb-cell{padding:4px 7px}.sb .sb-k{display:inline;margin-right:6px}.sb .sb-cell .sb-tag{font-size:12.5px;padding:1px 7px}.sb .sb-s{margin-top:1px}}`;
  function render(el,D,S,P,model){
    const m=(D.models||[]).find(x=>x.model===model); if(!m) {el.innerHTML=''; return;}
    const ml=modelLamp(m), mk=marketLamp(D), si=sectorInfo(S), pn=paperNote(P);
    const others=(D.models||[]).filter(x=>x.track!=='large'&&!x.retired&&x.model!==model&&x.regime_money).map(x=>{const l=modelLamp(x); return `<tr><td>${x.name}</td><td><span class="sb-tag sb-${l.state}">${l.word}</span></td><td class="sb-m">${l.detail}</td></tr>`;}).join('');
    const asof=D.asof&&D.asof.length===8?`${fd(D.asof)} 종가`:'';
    const mkWord=mk?(mk.bState==='win'?`과거 유사 칸: 대리 과매도가 시장보다 높았음`:mk.bState==='lose'?`과거 유사 칸: 대리 과매도가 시장보다 낮았음`:`과거 유사 칸: 차이를 못 가림`):'자료 없음';
    const e=mk&&E1[mk.cell];
    const mSub=(m.fix&&fin(m.fix.n))?`평가 완료 ${m.fix.n}목록 · 한 시기 기록`:'';
    const kSub=mk?`${e?`${e.n}신호일·${e.mo}개월 · 11년 대리`:''}${mk.kq?` · ${mk.kq}`:''}`:'';
    const sSub=si?`집계 가능한 ${si.total}업종 기준`:'';
    el.innerHTML=`<style>${CSS}</style><div class="sb"><h2>🚦 오늘 한 줄 <span class="sb-m">· ${asof} 기록 요약 · ${m.name} ${m.model} · 전부 지난 기록 — 매수 지시 아님</span></h2>
      <div class="sb-row"><div class="sb-cell"><div class="sb-k">모델</div><span class="sb-tag sb-${ml.state}">${ml.word}</span><span class="sb-s">${mSub}</span></div>
        <div class="sb-cell"><div class="sb-k">장세 <span class="sb-m">${mk?`코스피 20일 ${sg(mk.r20)}% · ${mk.label}`:''}</span></div><span class="sb-tag sb-${mk?mk.bState:'na'}">${mkWord}</span><span class="sb-s">${kSub}</span></div>
        <div class="sb-cell"><div class="sb-k">업종 <span class="sb-m">${si?`고점 대비 ${DEEP}% 이하 ${si.deep.length}개`:''}</span></div><span class="sb-tag sb-${si?'na':'low'}">${si?'하락만으로 제외할 근거 못 찾음':'업종 자료 없음'}</span><span class="sb-s">${sSub}</span></div></div>
      <div class="sb-con">→ ${conclusion(ml,mk)}</div>
      <div class="sb-m" style="margin-top:4px">${pn.head}</div>
      <details><summary>숫자·근거 · 다른 모델 · 뜻</summary><ul>
      <li><b>모델</b> ${ml.detail} <span class="sb-m">· 평가 완료 목록 기준 · 국면은 매수일이 아니라 추천일의 코스닥 20일선 · 평균의 구간(CI)은 없음</span></li>
      ${mk?`<li><b>장세</b> 코스피 20일 ${sg(mk.r20)}% = <b>${mk.label}</b>${mk.days?` ${mk.days}일째`:''} — ${mk.a}<br>${mk.b}${mk.kq?`<br><span class="sb-m">${mk.kq}</span>`:''}</li>`:''}
      <li><b>업종</b> ${sectorLine(si)}</li>
      ${pn.gate?`<li><b>게이트 계좌</b> ${pn.gate}</li>`:''}</ul><table>${others}</table>
      <div class="sb-m" style="margin-top:6px">뜻 — <b>모델</b>: 추천일의 코스닥 20일선 위/아래로 나눈 상승·약세 구간에 산 목록이 40거래일 뒤 같은 시장 전 종목 평균보다 나았나. 두 조건 = 평균 초과 > 0 그리고 시장보다 나은 목록 비율 ≥ 50%(구간별 10개 이상, 전체는 첫 표의 '자료 적음' 규칙). <b>장세</b>: 코스피 20거래일 등락을 여섯 칸으로 나눈 자리에서 11년간 (a) 시장이 40일 뒤 올랐나 (b) 과매도 대리(20일 수익 하위 20%, v30 아님)가 다음 거래일 진입 뒤 40일간 시장을 이겼나 — 구간이 0을 안 걸치면 "높았음/낮았음", 걸치면 "못 가림". 신호일·목록 수는 독립 시험 횟수가 아님. <b>업종</b>: 전체 업종 지도에서 20일 고점 대비 −20% 이하 업종 수(선택 목록 안 종목 수가 아님) — 경고가 아니라 사실. 세 줄은 따로 잰 기록이며 모델×장세×업종을 함께 시험한 결과가 아님. 규칙·문턱은 전부 이미 쓰던 값 · 근거 research/SIGNAL_BOARD_20261108.md.</div></details></div>`;
  }
  window.SignalBoard={mount:function(sel,opts){opts=opts||{}; const el=typeof sel==='string'?document.querySelector(sel):sel; if(!el) return;
    const q=f=>fetch(f+'?ts='+Date.now()).then(r=>r.ok?r.json():null).catch(()=>null);
    Promise.all([opts.scoreboard?Promise.resolve(opts.scoreboard):q('scoreboard.json'),q('sector_dd.json'),q('paper_account.json')]).then(([D,S,P])=>{try{if(D) render(el,D,S||null,P||{},opts.model||'v30');}catch(e){el.innerHTML='';}});}};
})();
