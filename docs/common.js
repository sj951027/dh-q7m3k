/* common.js — 전 페이지 공통 (2026-10-03, DISPLAY_TERMS.md 적용)
   · 맨 위 공통 메뉴  · 상태 줄(시험 기록: 날짜 + 쉬운 말 + 원래 용어)  · 맨 아래 고정 안내문과 용어 풀이
   표시 전용 — 점수·판정과 무관. 상태는 models_registry.json(판정·은퇴 단일 소스)에서 읽어 만든다.
   이 파일이 없거나 실패해도 각 페이지는 그대로 동작한다(전부 try 로 감쌈). */
(function () {
  'use strict';
  // 파일 → [모델 코드(없으면 null), 화면 이름, 종류: home|list|obs|ref]
  var PAGE = {
    'leaderboard.html': [null, '성적표', 'home'],
    'scoreboard.html': [null, '성적표', 'home'],
    'leaderboard_full.html': [null, '검증 자료', 'ref'],
    'guide.html': [null, '점수 읽는 법', 'ref'],
    'index.html': ['v30', '오늘의 과매도 목록 (과매도 v30)', 'list'],
    'filter.html': ['v30', '과매도 v30 목록', 'list'],
    'le.html': ['le_a', '저점탈출 le_a', 'list'],
    'lowvol.html': ['lv_b', '저변동 lv_b', 'list'],
    'sv.html': ['sv_a', '공매도비중 sv_a', 'list'],
    'px.html': ['px_a', '가격4팩터 px_a', 'list'],
    'lva.html': ['lv_a', '저변동+반전 lv_a', 'list'],
    'mom.html': ['mom_a', '모멘텀 mom_a', 'list'],
    'qs.html': ['qs_a', '조용한강자 qs_a', 'list'],
    'wu.html': ['wu_a', '전체종목 wu_a', 'list'],
    'mom_b.html': ['mom_b', '모멘텀+눌림 mom_b', 'list'],
    'filter_v31g.html': ['v31g', 'v31g 챌린저', 'list'],
    '_large_test.html': ['ls_t1', '대형밸류 ls_t1', 'list'],
    '_large_obs.html': [null, '대형 관측 리포트', 'obs'],
    'lead.html': ['ld_a', '주도주 ld_a', 'obs']
  };
  var MENU = [['leaderboard.html', '성적표'], ['filter.html', '과매도 v30'], ['le.html', '저점탈출 le_a'],
              ['lowvol.html', '저변동 lv_b'], ['_large_test.html', '대형'], ['leaderboard_full.html', '검증 자료']];
  var PLAIN = { '유의': '효과 확인됨', '기움': '확정 못 함', '노이즈': '차이 없음', '역작동': '반대로 감', '기각': '채택 안 함' };
  var NOTICE = '매수 추천이 아닙니다. 모델을 검증하는 기록이고, 투자 판단과 책임은 본인에게 있습니다.';
  var TERMS = [
    ['시험(검증 결론)', '미리 정한 기간·방법으로 한 번 본 결과입니다. 날짜가 붙어 있고, 그 뒤 성적이 바뀌어도 이 결과는 안 바뀝니다. 다시 보려면 새 기간을 미리 정합니다.'],
    ['효과 확인됨(유의)', '그 시험에서 점수 순서가 실제 수익 순서와 맞았고, 우연으로 보기 어려웠습니다.'],
    ['확정 못 함(기움)', '그 시험에서 좋은 쪽이었지만 우연일 가능성을 배제하지 못했습니다.'],
    ['차이 없음(노이즈)', '맞혔다고도 틀렸다고도 말할 수 없었습니다. "나쁘다"는 뜻이 아닙니다.'],
    ['반대로 감(역작동)', '점수가 높을수록 오히려 나빴습니다.'],
    ['검증 중', '미리 정한 기간(새 데이터 40거래일 등)이 아직 안 찼습니다.'],
    ['IC', '순서 맞힘 정도 — 점수 순서와 실제 수익 순서가 얼마나 같았는지(−1~+1, 0 근처면 무관).'],
    ['OOS', '모델을 등록한 뒤에 쌓인 새 데이터.'],
    ['앵커', '매수 기준일(그날 목록으로 샀다고 치는 날).'],
    ['유니버스', '후보 종목군.'],
    ['h5 · h20 · h40', '5일 뒤 · 20일 뒤 · 40일 뒤.'],
    ['%p', '퍼센트포인트 — 두 수익률의 차이. "시장보다 +3%p"는 시장이 +5%일 때 +8%였다는 뜻입니다.'],
    ['§11 · 정본', '미리 정한 검증 절차와, 그 절차로 낸 공식 결과.'],
    ['run_id', '기준일.'],
    ['가중 0 · 관측', '점수에 넣지 않고 기록만 하는 값.'],
    ['버킷(BUY/WAIT/OBSERVE/WATCH/EXCLUDE)', '과매도 v30 이 종목 상태를 나눈 칸입니다. BUY 도 매수 추천이 아니라 "조건을 다 채웠다"는 표시입니다.']
  ];

  function file() {
    var p = (location.pathname.split('/').pop() || 'index.html');
    return p === '' ? 'index.html' : p;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function mdOf(s) { var m = String(s || '').match(/(\d{1,2})\/(\d{1,2})/); return m ? (parseInt(m[1], 10) + '/' + parseInt(m[2], 10)) : ''; }

  // registry → 상태 문구(은퇴·시험 기록). 판정·은퇴가 바뀌면 models_registry.json 만 고치면 전 페이지에 반영된다.
  function statusOf(model, kind, reg) {
    reg = reg || {};
    var ret = (reg.retired || {})[model], sl = (reg.sealed || {})[model], parts = [];
    if (ret) parts.push('은퇴(' + mdOf(ret.date) + ')');
    if (sl && sl.v) {
      var d = mdOf(sl.short || sl.t), plain = PLAIN[sl.v] || sl.v;
      parts.push((d ? d + ' 시험: ' : '시험: ') + plain + (plain !== sl.v ? '(' + sl.v + ')' : ''));
    }
    if (parts.length) return parts.join(' · ');
    if (kind === 'obs') return '관측 전용';
    if (kind === 'list' && model) return '검증 중';
    return '';
  }
  window.__gxStatusOf = statusOf;   // 다른 스크립트·테스트에서 재사용

  function css() {
    var s = document.createElement('style');
    s.textContent =
      '.gx-nav{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;padding:8px 12px;margin:0 0 10px;font-size:13px;line-height:1.5;' +
      'border-bottom:1px solid rgba(128,128,128,.3);font-family:inherit}' +
      '.gx-nav a{color:inherit;text-decoration:none;opacity:.72}.gx-nav a:hover{opacity:1;text-decoration:underline}' +
      '.gx-nav a.gx-on{opacity:1;font-weight:700;border-bottom:2px solid currentColor}' +
      '.gx-status{padding:6px 12px;margin:0 0 12px;font-size:13px;line-height:1.5;border-left:3px solid rgba(128,128,128,.55);background:rgba(128,128,128,.09)}' +
      '.gx-status b{font-weight:700}' +
      '.gx-foot{margin:28px 0 8px;padding:12px;font-size:12px;line-height:1.6;opacity:.85;border-top:1px solid rgba(128,128,128,.3)}' +
      '.gx-foot summary{cursor:pointer}.gx-foot dl{margin:8px 0 0}.gx-foot dt{font-weight:700;margin-top:6px}.gx-foot dd{margin:0 0 0 0}';
    document.head.appendChild(s);
  }

  function render(reg) {
    var f = file(), pg = PAGE[f] || [null, '', 'ref'], model = pg[0], name = pg[1], kind = pg[2];
    var nav = document.createElement('nav'); nav.className = 'gx-nav';
    nav.innerHTML = MENU.map(function (m) {
      var on = (m[0] === f) || (f === 'scoreboard.html' && m[0] === 'leaderboard.html');
      return '<a href="' + m[0] + '"' + (on ? ' class="gx-on"' : '') + '>' + esc(m[1]) + '</a>';
    }).join('');
    var first = document.body.firstChild;
    document.body.insertBefore(nav, first);
    var st = statusOf(model, kind, reg);
    if (name && (kind === 'list' || kind === 'obs')) {
      var bar = document.createElement('div'); bar.className = 'gx-status';
      bar.innerHTML = '<b>' + esc(name) + '</b>' + (st ? ' · ' + esc(st) : '');
      document.body.insertBefore(bar, nav.nextSibling);
      try { document.title = name + (st ? ' · ' + st : ''); } catch (e) {}
    }
    var foot = document.createElement('div'); foot.className = 'gx-foot';
    foot.innerHTML = esc(NOTICE) + '<details><summary>용어 풀이</summary><dl>' +
      TERMS.map(function (t) { return '<dt>' + esc(t[0]) + '</dt><dd>' + esc(t[1]) + '</dd>'; }).join('') + '</dl></details>';
    document.body.appendChild(foot);
  }

  function start() {
    try { css(); } catch (e) {}
    var done = false;
    function go(reg) { if (done) return; done = true; try { render(reg); } catch (e) {} }
    try {
      fetch('models_registry.json?ts=' + Date.now()).then(function (r) { return r.ok ? r.json() : {}; })
        .then(go).catch(function () { go({}); });
      setTimeout(function () { go({}); }, 4000);   // registry 가 늦으면 상태 없이라도 메뉴는 띄운다
    } catch (e) { go({}); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
