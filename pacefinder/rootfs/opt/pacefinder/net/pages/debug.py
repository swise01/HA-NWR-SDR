DEBUG_PERF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder · Perf Inspector</title>
<link rel="stylesheet" href="/static/tokens.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--color-bg);color:var(--color-text-primary);font-family:var(--font-mono);min-height:100vh}
.tb{height:50px;display:flex;align-items:center;padding:0 var(--space-4);gap:14px;border-bottom:1px solid var(--color-border);position:sticky;top:0;background:var(--color-bg);z-index:10}
.tb h1{font-size:var(--text-md);color:var(--color-text-primary);letter-spacing:3px;text-transform:uppercase;flex:1}
.tb a{font-size:var(--text-xs);color:var(--color-text-secondary);letter-spacing:1px;text-transform:uppercase;text-decoration:none}
.tb a:hover{color:var(--color-text-primary)}
section{padding:14px var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
h2{font-size:var(--text-xs);color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:1px;font-weight:normal;padding:6px 10px;text-align:right;border-bottom:1px solid var(--color-border);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td{padding:5px 10px;border-bottom:1px dotted var(--n-900);text-align:right;font-variant-numeric:tabular-nums}
tr.slow td{color:var(--warn,#f59e0b)}
tr.crit td{color:var(--danger,#ef4444)}
.summary{display:flex;gap:24px;flex-wrap:wrap;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:10px}
.summary b{color:var(--color-text-primary);font-weight:var(--fw-medium)}
.empty{padding:30px;text-align:center;color:var(--color-text-muted);font-size:var(--text-xs)}
</style>
</head>
<body>
<div class="tb">
  <h1>Perf Inspector</h1>
  <a href="/debug/raw">Raw Telemetry</a>
  <a href="/">Dashboard</a>
</div>
<section>
  <h2>Server requests (last 200, slowest first)</h2>
  <div id="srv-summary" class="summary"></div>
  <div id="srv-empty" class="empty">No requests yet — browse around to populate.</div>
  <table id="srv-tbl" style="display:none">
    <thead><tr><th>path</th><th>method</th><th>n</th><th>p50 ms</th><th>p95 ms</th><th>max ms</th><th>db ms (avg)</th><th>bytes (avg)</th></tr></thead>
    <tbody></tbody>
  </table>
</section>
<section>
  <h2>Client page renders (last 200)</h2>
  <div id="cli-empty" class="empty">No client reports yet — load an instrumented page.</div>
  <table id="cli-tbl" style="display:none">
    <thead><tr><th>path</th><th>n</th><th>marks (avg ms)</th></tr></thead>
    <tbody></tbody>
  </table>
</section>
<script>
function pct(arr,p){if(!arr.length)return 0;const s=[...arr].sort((a,b)=>a-b);return s[Math.min(s.length-1,Math.floor(s.length*p))];}
function aggSrv(rows){
  const by={};
  for(const r of rows){const k=r.path;(by[k]=by[k]||[]).push(r);}
  const out=[];
  for(const [path,rs] of Object.entries(by)){
    const totals=rs.map(r=>r.total_ms);
    const dbs=rs.map(r=>r.db_ms);
    const bs=rs.map(r=>r.bytes);
    out.push({path, n:rs.length,
      p50:pct(totals,.5).toFixed(1),
      p95:pct(totals,.95).toFixed(1),
      max:Math.max(...totals).toFixed(1),
      db:(dbs.reduce((a,b)=>a+b,0)/dbs.length).toFixed(1),
      bytes:Math.round(bs.reduce((a,b)=>a+b,0)/bs.length),
    });
  }
  out.sort((a,b)=>parseFloat(b.p95)-parseFloat(a.p95));
  return out;
}
function aggCli(rows){
  const by={};
  for(const r of rows){const k=r.path;(by[k]=by[k]||[]).push(r);}
  const out=[];
  for(const [path,rs] of Object.entries(by)){
    const markKeys=new Set();
    for(const r of rs)for(const k of Object.keys(r.marks||{}))markKeys.add(k);
    const avgs={};
    for(const k of markKeys){
      const vs=rs.map(r=>r.marks?.[k]).filter(v=>typeof v==='number');
      if(vs.length)avgs[k]=(vs.reduce((a,b)=>a+b,0)/vs.length).toFixed(1);
    }
    out.push({path, n:rs.length, marks:avgs});
  }
  return out;
}
async function refresh(){
  try{
    const d=await fetch('/debug/perf?json=1',{cache:'no-store'}).then(r=>r.json());
    const srv=aggSrv(d.server||[]);
    const tblS=document.querySelector('#srv-tbl tbody');
    const empS=document.getElementById('srv-empty');
    if(srv.length){
      empS.style.display='none';document.getElementById('srv-tbl').style.display='';
      tblS.innerHTML=srv.map(r=>{
        const cls=r.p95>=500?'crit':(r.p95>=100?'slow':'');
        return `<tr class="${cls}"><td>${r.path}</td><td>—</td><td>${r.n}</td><td>${r.p50}</td><td>${r.p95}</td><td>${r.max}</td><td>${r.db}</td><td>${r.bytes}</td></tr>`;
      }).join('');
    }
    const sum=document.getElementById('srv-summary');
    sum.innerHTML=`<span>Tracked: <b>${(d.server||[]).length}</b></span><span>Distinct paths: <b>${srv.length}</b></span>`;
    const cli=aggCli(d.client||[]);
    const tblC=document.querySelector('#cli-tbl tbody');
    const empC=document.getElementById('cli-empty');
    if(cli.length){
      empC.style.display='none';document.getElementById('cli-tbl').style.display='';
      tblC.innerHTML=cli.map(r=>{
        const marks=Object.entries(r.marks).map(([k,v])=>`${k}=${v}`).join(' ');
        return `<tr><td>${r.path}</td><td>${r.n}</td><td>${marks||'—'}</td></tr>`;
      }).join('');
    }
  }catch(e){}
}
setInterval(refresh,2000);
refresh();
</script>
</body>
</html>
"""

DEBUG_RAW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder · Raw Telemetry</title>
<link rel="stylesheet" href="/static/tokens.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--color-bg);color:var(--color-text-primary);font-family:var(--font-mono);min-height:100vh}
.tb{height:50px;display:flex;align-items:center;padding:0 var(--space-4);gap:14px;border-bottom:1px solid var(--color-border);position:sticky;top:0;background:var(--color-bg);z-index:10}
.tb h1{font-size:var(--text-md);color:var(--color-text-primary);letter-spacing:3px;text-transform:uppercase;flex:1}
.tb a{font-size:var(--text-xs);color:var(--color-text-secondary);letter-spacing:1px;text-transform:uppercase;text-decoration:none}
.tb a:hover{color:var(--color-text-primary)}
.meta{padding:14px var(--space-4);border-bottom:1px solid var(--color-border-subtle);font-size:var(--text-xs);color:var(--color-text-secondary);display:flex;gap:24px;flex-wrap:wrap}
.meta b{color:var(--color-text-primary);font-weight:var(--fw-medium)}
.search{padding:8px var(--space-4);border-bottom:1px solid var(--color-border-subtle)}
.search input{width:100%;max-width:420px;background:var(--color-surface);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:inherit;font-size:var(--text-sm);padding:6px 10px;border-radius:var(--radius-sm)}
.grid{padding:14px var(--space-4);display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:0 24px}
.row{display:flex;justify-content:space-between;font-size:.78rem;padding:3px 0;border-bottom:1px dotted var(--n-900)}
.row.changed{background:rgba(74,154,239,.06)}
.k{color:var(--color-text-secondary)}
.v{color:var(--color-text-primary);font-variant-numeric:tabular-nums}
.empty{padding:60px;text-align:center;color:var(--color-text-muted)}
</style>
</head>
<body>
<div class="tb">
  <h1>Raw Telemetry</h1>
  <a href="/">Dashboard</a>
  <a href="/sessions">Sessions</a>
</div>
<div class="meta">
  <span>Game: <b id="m-game">—</b></span>
  <span>Packet rate: <b id="m-rate">—</b></span>
  <span>Last update: <b id="m-age">—</b></span>
  <span>Fields: <b id="m-count">0</b></span>
</div>
<div class="search"><input id="filter" type="text" placeholder="Filter fields (e.g. wheel, slip, lane)…"></div>
<div id="grid" class="grid"></div>
<div id="empty" class="empty">Waiting for telemetry… start a race in Forza.</div>
<script>
const grid=document.getElementById('grid');
const empty=document.getElementById('empty');
const filterEl=document.getElementById('filter');
let prev={}, lastTs=null, rateBuf=[];
function fmt(v){
  if(v===null||v===undefined)return '—';
  if(typeof v==='number')return Math.abs(v)>=1000?v.toFixed(0):v.toFixed(4).replace(/\\.?0+$/,'');
  if(typeof v==='boolean')return v?'true':'false';
  return String(v);
}
function tick(d){
  const now=performance.now();
  if(lastTs!==null){rateBuf.push(now-lastTs);if(rateBuf.length>30)rateBuf.shift();}
  lastTs=now;
  const avg=rateBuf.length?(rateBuf.reduce((a,b)=>a+b,0)/rateBuf.length):0;
  document.getElementById('m-rate').textContent=avg?(1000/avg).toFixed(1)+' Hz':'—';
  document.getElementById('m-game').textContent=d._game||'—';
  document.getElementById('m-age').textContent=new Date().toLocaleTimeString();
  const keys=Object.keys(d).filter(k=>k!=='_game'&&k!=='_packet_type').sort();
  document.getElementById('m-count').textContent=keys.length;
  if(!keys.length){empty.style.display='';grid.innerHTML='';return;}
  empty.style.display='none';
  const f=filterEl.value.toLowerCase();
  let html='';
  for(const k of keys){
    if(f && !k.toLowerCase().includes(f))continue;
    const v=d[k], pv=prev[k];
    const changed=(pv!==undefined && pv!==v)?' changed':'';
    html+=`<div class="row${changed}"><span class="k">${k}</span><span class="v">${fmt(v)}</span></div>`;
  }
  grid.innerHTML=html;
  prev=d;
}
async function poll(){
  try{
    const d=await fetch('/debug/raw.json',{cache:'no-store'}).then(r=>r.json());
    tick(d);
  }catch(e){}
}
setInterval(poll,200);
poll();
filterEl.addEventListener('input',()=>tick(prev));
</script>
</body>
</html>
"""
