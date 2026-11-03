const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=path.resolve(__dirname,'../../..');
const result=[];
for (const name of ['filter','lowvol','lva','le','sv','qs','px','mom']) {
  const src=fs.readFileSync(path.join(root,'docs',name+'.html'),'utf8');
  let scripts=0;
  for (const match of src.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
    if(match[1].trim()) {new vm.Script(match[1],{filename:name+'.html'});scripts++;}
  }
  const fn=name==='filter'?'formatCell':'fmt';
  const code=src.match(new RegExp('function '+fn+'\\([^)]*\\)\\s*\\{[\\s\\S]*?^\\}','m'))[0];
  const ctx=vm.createContext({});vm.runInContext(code,ctx);
  const render=v=>name==='filter'?ctx.formatCell({earn_recent_20d:v},{key:'earn_recent_20d',type:'earnrecent'}):ctx.fmt(v,'recentern');
  for(const v of ['접수 3일(↓)','접수 12일(↑)','접수 0일','접수 19일']) {
    const html=render(v);assert(html.includes(v));assert(html.includes('#4a5568'));assert(!html.includes('📉'));
  }
  for(const v of ['',undefined,null,'nan','None','<img src=x onerror=alert(1)>']) {
    const html=render(v);assert(!html.includes('접수'));assert(!html.includes('<img'));
  }
  if(name==='filter') {
    const f=src.match(/function loadColumnPrefs\([^)]*\)\s*\{[\s\S]*?^\}/m)[0];
    function preferences(saved) {
      const data=new Map(saved?[['csv_filter_visible_cols_v2',JSON.stringify(['name','earn_drop_60d'])],['csv_filter_r3m_cols_20260930','1'],['csv_filter_earn_col_20261004','1']]:[]);
      const localStorage={getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)};
      const c=vm.createContext({localStorage});
      vm.runInContext("var visibleColumns=null; var DEFAULT_COLUMNS=['name','earn_drop_60d','earn_recent_20d'];"+f,c);
      c.loadColumnPrefs();assert(c.visibleColumns.has('earn_recent_20d'));
      c.visibleColumns.delete('earn_recent_20d');data.set('csv_filter_visible_cols_v2',JSON.stringify([...c.visibleColumns]));
      c.loadColumnPrefs();assert(!c.visibleColumns.has('earn_recent_20d'));
    }
    preferences(true);preferences(false);
  }
  result.push({page:name,inlineScripts: scripts,status:'PASS',checks:'JS syntax, gray labels/empty input, no raw HTML injection'+(name==='filter'?', existing/new column preferences preserve later opt-out':'')});
}
fs.writeFileSync(path.join(__dirname,'pages_check.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
