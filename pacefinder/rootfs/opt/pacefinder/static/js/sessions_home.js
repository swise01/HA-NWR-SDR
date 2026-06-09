const GL={'forza_motorsport':'Forza','forza_horizon_5':'Horizon','acc':'ACC','f1':'F1'};
const GD={'forza_motorsport':'Forza Motorsport / Horizon','acc':'Assetto Corsa Competizione','f1':'F1 2023 / 2024'};
function fmtLap(s){if(!s)return'—';const m=Math.floor(s/60),r=s%60;return m+':'+(r<10?'0':'')+r.toFixed(3);}
function fmtDate(iso){if(!iso)return'—';return new Date(iso).toLocaleDateString([],{month:'short',day:'numeric',year:'numeric'});}
function fmtRel(iso){if(!iso)return'';const d=new Date(iso),n=Date.now(),s=Math.floor((n-d)/1000);if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago';}
function p1(v,d=1){return v==null?null:parseFloat(v.toFixed(d));}

// Default to 'all' so the Form chart populates with whatever sessions exist
// (time_trial, hot_lap, etc. — not just multi-driver 'real' races). See #17.
let _type='all',_last=10;
let _allTracks=[],_allRecent=[],_allFormData=[];

// ── KPI cards ─────────────────────────────────────────────────
function setKV(id,val){const el=document.getElementById(id);if(val==null||val==='—'){el.textContent='—';el.classList.add('dash');}else{el.textContent=val;el.classList.remove('dash');}}
async function loadKPIs(){
  let k={};
  try{k=await fetch('/sessions/career').then(r=>r.json());}catch(e){}
  const t=k.total_sessions||0,rc=k.real_count||0,ai=k.ai_count||0;
  setKV('kv-total',t||'0');
  document.getElementById('ks-total').textContent=t?(rc+' real · '+ai+' AI'):'';
  const af=k.avg_finish_real;
  setKV('kv-finish',af!=null?'P'+p1(af):null);
  const pg=k.avg_pos_gained;
  setKV('kv-gained',pg!=null?(pg>=0?'+':'')+p1(pg):null);
  // Color the gained KPI by sign: green when actually gaining, red when losing.
  const pgEl=document.getElementById('kv-gained');
  if(pgEl){pgEl.classList.toggle('green', pg>0); pgEl.classList.toggle('red', pg<0);}
  setKV('kv-win',k.win_rate!=null?p1(k.win_rate,0)+'%':null);
  setKV('kv-podium',k.podium_rate!=null?p1(k.podium_rate,0)+'%':null);
  setKV('kv-laps',k.total_laps||'0');
  document.getElementById('ks-circuits').textContent=(k.circuit_count||0)+' circuits';
}

// ── Tab counts ────────────────────────────────────────────────
async function loadTabCounts(){
  let games=[];
  try{games=await fetch('/sessions/games').then(r=>r.json());}catch(e){}
  const totals={};
  let all=0;
  games.forEach(g=>{totals[g.game]=g.session_count||0;all+=g.session_count||0;});
  document.getElementById('cnt-all').textContent=all?'('+all+')':'';
  document.getElementById('cnt-forza').textContent=(totals['forza_motorsport']||0)?'('+(totals['forza_motorsport']||0)+')':'';
  document.getElementById('cnt-acc').textContent=(totals['acc']||0)?'('+(totals['acc']||0)+')':'';
  document.getElementById('cnt-f1').textContent=(totals['f1']||0)?'('+(totals['f1']||0)+')':'';
  renderGames(games);
}

// ── Trend spark ───────────────────────────────────────────────
function posToPercentile(fp){if(fp==null)return null;return Math.max(5,Math.min(100,Math.round(100-(fp-1)*6)));}

function renderTrendSpark(){
  const data=_allFormData;
  const el=document.getElementById('trend-spark');
  const withPos=data.filter(s=>s.finish_pos!=null);
  if(withPos.length<2){el.innerHTML='';return;}
  const pcts=withPos.map(s=>posToPercentile(s.finish_pos));
  const w=400,h=44,pad=3;
  const mn=Math.min(...pcts),mx=Math.max(...pcts);
  const span=Math.max(mx-mn,15);
  const lo=Math.max(0,mn-span*0.10),hi=Math.min(100,mx+span*0.10);
  const rng=hi-lo;
  const xs=pcts.map((_,i)=>pad+(w-pad*2)*i/Math.max(pcts.length-1,1));
  const ys=pcts.map(v=>h-pad-(h-pad*2)*(v-lo)/rng);
  const pts=xs.map((x,i)=>x.toFixed(1)+','+ys[i].toFixed(1)).join(' ');
  const half=Math.floor(pcts.length/2);
  const a1=pcts.slice(0,half).reduce((a,b)=>a+b,0)/(half||1);
  const a2=pcts.slice(half).reduce((a,b)=>a+b,0)/((pcts.length-half)||1);
  const diff=a2-a1;
  const col=diff>4?'#22c55e':diff<-4?'#ef4444':'#888';
  const lx=xs[xs.length-1],ly=ys[ys.length-1];
  el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%">
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" opacity=".85"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3" fill="${col}" opacity=".9"/>
  </svg>`;
}

// ── Form chart ────────────────────────────────────────────────
function renderForm(){
  const data=_allFormData;
  const sliced=data.slice(-_last);
  const el=document.getElementById('form-chart');
  if(!sliced.length){el.innerHTML='<div class="form-empty">No race data<small>Finish position data needed — check session race_type classification.</small></div>';updateFormMeta([]);return;}
  el.innerHTML=sliced.map(s=>{
    const pct=posToPercentile(s.finish_pos);
    const h=pct!=null?Math.round(pct+20):0;
    const col=pct!=null?`hsl(${h},70%,38%)`:'#1a1a1a';
    const ht=pct!=null?(pct+'% &bull; P'+s.finish_pos+' &bull; '+(s.track||'?')):'(no pos) &bull; '+(s.track||'?');
    const hpct=pct!=null?pct:20;
    return`<div class="bar" style="height:${hpct}%;background:${col}">
      <div class="bar-tip">${ht}</div>
    </div>`;
  }).join('');
  updateFormMeta(sliced);
}
async function loadFormData(){
  try{_allFormData=await fetch('/sessions/form?type='+_type+'&last=50').then(r=>r.json());}catch(e){_allFormData=[];}
  renderForm();
  renderTrendSpark();
}
function updateFormMeta(data){
  const el=document.getElementById('form-trend');
  const pctEl=document.getElementById('form-pct');
  const noteEl=document.getElementById('form-note');
  const withPos=data.filter(s=>s.finish_pos!=null);
  if(!withPos.length){el.textContent='';el.className='form-trend fl';pctEl.textContent='';noteEl.textContent='';return;}
  const pcts=withPos.map(s=>posToPercentile(s.finish_pos));
  const avg=pcts.reduce((a,b)=>a+b,0)/pcts.length;
  const half=Math.floor(pcts.length/2);
  const first=pcts.slice(0,half),second=pcts.slice(half);
  const avgFirst=first.length?first.reduce((a,b)=>a+b,0)/first.length:avg;
  const avgSecond=second.length?second.reduce((a,b)=>a+b,0)/second.length:avg;
  const diff=avgSecond-avgFirst;
  if(diff>4){el.textContent='▲ Improving';el.className='form-trend up';}
  else if(diff<-4){el.textContent='▼ Declining';el.className='form-trend dn';}
  else{el.textContent='— Steady';el.className='form-trend fl';}
  pctEl.textContent='Top '+Math.round(100-avg)+'% avg finish';
  noteEl.textContent=withPos.length+' sessions with position data';
}

// ── Filter toggles ────────────────────────────────────────────
// Race-type filter (Real/AI/All) was removed per user feedback —
// keep race_type data + display it as a per-row pill, no top-of-page filter.
document.getElementById('last-filters').addEventListener('click',e=>{
  const b=e.target.closest('.ftog');if(!b)return;
  document.querySelectorAll('#last-filters .ftog').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');_last=+b.dataset.val;renderForm();
});

// ── Tracks (pills + table) ────────────────────────────────────
async function loadTracks(){
  try{_allTracks=await fetch('/sessions/tracks').then(r=>r.json());}catch(e){_allTracks=[];}
  renderTracks();
}
function renderTracks(){
  const tracks=_allTracks;
  // pills
  const pr=document.getElementById('pills-row');
  const withLap=tracks.filter(t=>t.best_lap_time_s);
  pr.innerHTML=withLap.length?withLap.map(t=>{
    const esc=encodeURIComponent(t.track);
    const label=t.track==='unknown'?'Unknown Track':t.track;
    const unres=/^Track #\d+$/.test(t.track);
    return`<div class="pill${unres?' unresolved':''}" onclick="location.href='/sessions/track?name=${esc}'">
      <div class="pill-circuit">${label}</div>
      <div class="pill-time">${fmtLap(t.best_lap_time_s)}</div>
    </div>`;
  }).join(''):'<span style="font-size:var(--text-sm);color:var(--color-text-muted)">No lap data yet</span>';
  // table
  const tbody=document.getElementById('circuit-tbody');
  if(!tracks.length){tbody.innerHTML='<tr><td colspan="5" style="color:var(--color-text-muted);font-size:var(--text-sm);padding:20px 14px">No sessions yet</td></tr>';return;}
  tbody.innerHTML=tracks.map(t=>{
    const trend=t.trend==='up'?'<span class="td-trend-up">▲</span>':t.trend==='dn'?'<span class="td-trend-dn">▼</span>':'<span class="td-trend-fl">—</span>';
    const esc=encodeURIComponent(t.track);
    const label=t.track==='unknown'?'Unknown Track':t.track;
    const avgFinish=t.avg_finish!=null?`<span class="td-blue">${t.avg_finish}</span>`:`<span class="td-blue dim">—</span>`;
    const bestLap=t.best_lap_time_s?`<span class="td-amber">${fmtLap(t.best_lap_time_s)}</span>`:`<span style="color:var(--color-text-dim)">—</span>`;
    return`<tr onclick="location.href='/sessions/track?name=${esc}'">
      <td class="td-track">${label}</td>
      <td class="td-num">${t.session_count}</td>
      <td>${avgFinish}</td>
      <td>${bestLap}</td>
      <td>${trend}</td>
    </tr>`;
  }).join('');
}

// ── Game cards ────────────────────────────────────────────────
function sparkSVG(vals){
  if(!vals||!vals.length)return'';
  const w=120,h=28,pad=2;
  const mn=Math.min(...vals),mx=Math.max(...vals),rng=mx-mn||1;
  const xs=vals.map((_,i)=>pad+(w-pad*2)*i/Math.max(vals.length-1,1));
  const ys=vals.map(v=>h-pad-(h-pad*2)*(v-mn)/rng);
  const pts=xs.map((x,i)=>x+','+ys[i]).join(' ');
  return`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" class="gc-spark">
    <polyline points="${pts}" fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity=".8"/>
  </svg>`;
}
function renderGames(games){
  const grid=document.getElementById('games-grid');
  if(!games.length){grid.innerHTML='<div style="color:var(--color-text-muted);font-size:var(--text-sm);padding:20px">No sessions</div>';return;}
  grid.innerHTML=games.map(g=>{
    const label=GL[g.game]||g.game;
    const desc=GD[g.game]||'';
    const empty=!g.session_count;
    const last=fmtDate(g.last_played);
    const spark=sparkSVG(g.spark||[]);
    // Build the onclick separately to avoid escaping hell in the inline
    // attribute. data-game is read by the click handler at the bottom.
    const cls='gc'+(empty?' empty':'');
    return`<div class="${cls}" data-game="${g.game}">
      <div class="gc-name">${label}</div>
      <div class="gc-desc">${desc}</div>
      <div class="gc-stats">
        <div class="gc-stat"><div class="v">${g.session_count||0}</div><div class="l">Sessions</div></div>
        <div class="gc-stat"><div class="v">${g.track_count||0}</div><div class="l">Circuits</div></div>
      </div>
      ${g.best_lap_time_s?`<div class="gc-best">${fmtLap(g.best_lap_time_s)} <span>at ${g.best_lap_track||'?'}</span></div>`:''}
      ${spark}
      <div class="gc-last">${last?('Last: '+last+(g.last_played_track?' &bull; '+g.last_played_track:'')):'No sessions yet'}</div>
    </div>`;
  }).join('');
  // Delegated click — non-empty cards navigate to that game's overview.
  grid.querySelectorAll('.gc:not(.empty)').forEach(el=>{
    el.addEventListener('click',()=>{
      location.href='/sessions/game?name='+encodeURIComponent(el.dataset.game);
    });
  });
}

// ── Recent feed ───────────────────────────────────────────────
async function loadRecent(){
  try{_allRecent=await fetch('/sessions/recent').then(r=>r.json());}catch(e){_allRecent=[];}
  renderRecent();
}
function renderRecent(){
  const sessions=_allRecent;
  const feed=document.getElementById('recent-feed');
  if(!sessions.length){feed.innerHTML='<div style="color:var(--color-text-muted);font-size:var(--text-sm);padding:20px">No sessions yet</div>';return;}
  feed.innerHTML=sessions.map(s=>{
    const gameKey=s.game==='forza_motorsport'||s.game==='forza_horizon_5'?'forza':s.game||'?';
    const label=(GL[s.game]||s.game||'?').toUpperCase();
    const fp=s.finish_pos,gp=s.grid_pos;
    let posHtml='';
    // Grid → Finish (gained). Grid badge is muted; finish keeps the existing color cues.
    if(gp!=null && gp>0){
      posHtml+=`<span class="recent-grid">P${gp}</span><span class="recent-arrow">→</span>`;
    }
    if(fp!=null){
      const cls=fp===1?'p1':fp<=3?'podium':'ok';
      posHtml+=`<span class="recent-pos ${cls}">P${fp}</span>`;
    }
    let gainedHtml='';
    if(fp!=null&&gp!=null&&gp>0){
      const g=gp-fp;
      const cls=g>0?'pos':g<0?'neg':'neu';
      gainedHtml=`<span class="recent-gained ${cls}">${g>0?'+':''}${g}</span>`;
    }
    const WX_ICON={'Clear':'☀','LightCloud':'⛅','Overcast':'☁','LightRain':'🌦','Rain':'🌧','HeavyRain':'⛈','Thunderstorm':'⛈'};
    const wxHtml=s.weather_condition?`<span class="recent-wx" title="${s.weather_condition}${s.track_temp_c!=null?' · '+s.track_temp_c.toFixed(0)+'°C':''}">${WX_ICON[s.weather_condition]||''}</span>`:'';
    const href="/sessions/session?id="+encodeURIComponent(s.session_id)+"&game="+encodeURIComponent(s.game||'')+"&track="+encodeURIComponent(s.track||'');
    return`<div class="recent-row" onclick="location.href='${href}'">
      <span class="recent-badge ${gameKey}">${label}</span>
      <span class="recent-circuit">${s.track||'Unknown'}</span>
      <span class="recent-date">${fmtRel(s.started_at)}</span>
      <span class="recent-lap">${fmtLap(s.best_lap_time_s)}</span>
      ${wxHtml}
      ${posHtml}
      ${gainedHtml}
    </div>`;
  }).join('');
}

// ── Boot ─────────────────────────────────────────────────────
// Career page: KPIs + tab counts + form trend only. Tracks / recent /
// game-cards were trimmed (Home + circuit/car pages cover those) so
// their loaders are no longer called — the functions remain for any
// future reuse but target DOM that no longer exists on this page.
Promise.all([loadKPIs(),loadTabCounts(),loadFormData()]);
