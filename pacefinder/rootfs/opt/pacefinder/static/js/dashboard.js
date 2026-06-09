const $=id=>document.getElementById(id);
// Forza UDP lap_number is 0-indexed (race lap 1 = lap_number 0). Forza's
// on-screen "Lap N" is 1-indexed, so add 1 for display. ACC support is
// parked; if/when it returns, gate this on game.
const lapLabel = n => (n == null ? '—' : 'L' + (Number(n) + 1));
const es=new EventSource('/stream');
let _maxRpm=8500,_dbgEs=null,_dbgOpen=false,_bestLap=null;
let state_sid=null;
const _dbgLines=[];
const _flashTimers={};

// Track-records cache — flips when the live track changes. Avoids
// per-packet refetches; this is static context for the live values.
let _lastRecordsTrack = null;
function fmtLapStatic(s){
  if(s == null) return '—';
  const m = Math.floor(s / 60);
  return m + ':' + (s % 60).toFixed(3).padStart(6, '0');
}
async function loadTrackRecords(track){
  let r;
  try{ r = await fetch('/dashboard/records?track=' + encodeURIComponent(track))
        .then(x => x.json()); }
  catch(e){ return; }
  // Guard against a track change firing between request and response —
  // only paint records that still match the current live track.
  if(track !== _lastRecordsTrack) return;
  const pbEl  = $('t-pb'), pbVal  = $('t-pb-val');
  const bfEl  = $('t-bf'), bfVal  = $('t-bf-val');
  if(r && r.best_lap_time_s != null){
    pbVal.textContent = fmtLapStatic(r.best_lap_time_s);
    pbEl.style.display = '';
  } else { pbEl.style.display = 'none'; }
  if(r && r.best_finish_pos != null){
    bfVal.textContent = 'P' + r.best_finish_pos;
    bfEl.style.display = '';
  } else { bfEl.style.display = 'none'; }
}
function hideTrackRecords(){
  const pbEl = $('t-pb'); if(pbEl) pbEl.style.display = 'none';
  const bfEl = $('t-bf'); if(bfEl) bfEl.style.display = 'none';
}
// Check ?edit=<sid> on load — open confirm modal for that session
const _editSid=new URLSearchParams(location.search).get('edit');
if(_editSid) setTimeout(()=>openFinish(_editSid),600);

function flash(id){
  const el=$(id); if(!el)return;
  if(_flashTimers[id])clearTimeout(_flashTimers[id]);
  el.classList.remove('flash');
  void el.offsetWidth; // reflow to restart animation
  el.classList.add('flash');
  _flashTimers[id]=setTimeout(()=>el.classList.remove('flash'),400);
}

function fmt(s){
  if(s==null)return'—';
  const m=Math.floor(s/60);
  return m+':'+(s%60).toFixed(3).padStart(6,'0');
}

function slipColor(v){
  if(v<0.1)return'#22c55e';
  if(v<0.3)return'#f59e0b';
  return'#ef4444';
}

function tyreClass(t){
  if(t==null)return'na';
  if(t<170)return'cold';
  if(t<=210)return'ok';
  if(t<=230)return'hot';
  return'over';
}

let _liveGame=null;
function setSlip(pfx,val){
  const v=val??0;
  // ACC wheelSlip is in m/s (0–3 range); Forza/F1 are dimensionless ratios (0–1 range)
  const scale=(_liveGame==='acc')?0.5:0.5;
  const pct=Math.min(100,v/scale*100);
  const col=slipColor(v/scale*0.5);
  $(pfx+'-b').style.height=pct+'%';
  $(pfx+'-b').style.background=col;
  $(pfx+'-v').textContent=val!=null?v.toFixed(3):'—';
}

es.onmessage=e=>{
  const d=JSON.parse(e.data);
  const recv=d.status==='receiving';
  const ended=d.status==='race_ended';

  // topbar
  $('dot').className='dot '+(recv?'receiving':ended?'race_ended':'idle');
  $('tb-stat').textContent=ended?'RACE ENDED':(d.status||'IDLE').toUpperCase();
  $('tb-stat').className='tb-stat'+(recv?' receiving':ended?' race_ended':'');
  const gameLabels={'forza_motorsport':'Forza Motorsport','forza_horizon_5':'Forza Horizon','acc':'ACC','f1':'F1 2024'};
  const gameClsMap={'forza_motorsport':'forza','forza_horizon_5':'forza','acc':'acc','f1':'f1'};
  const gEl=$('tb-game');
  gEl.textContent=d.game?gameLabels[d.game]||d.game.replace(/_/g,' ').toUpperCase():'—';
  gEl.className='tb-game game-'+(d.game?gameClsMap[d.game]||'none':'none');
  $('tb-track').textContent=d.track&&d.track!=='unknown'?d.track:'—';
  // Track-record lookup — fires once per track-change (or on first
  // packet of a fresh session). Cheap aggregate hit, never re-fired
  // per packet. See loadTrackRecords() below.
  if(d.track && d.track !== 'unknown' && d.track !== _lastRecordsTrack){
    _lastRecordsTrack = d.track;
    loadTrackRecords(d.track);
  } else if(!d.track || d.track === 'unknown'){
    _lastRecordsTrack = null;
    hideTrackRecords();
  }
  // Car name + class badge + PI. Class derived from PI via shared
  // pfCarClass() (FM2023 ranges) — see static/js/class.js.
  const carName=d.car&&d.car!=='unknown'?d.car:null;
  const hasCar=!!(carName||d.car_class!=null||d.car_pi!=null);
  $('tb-car-sep').style.display=hasCar?'inline':'none';
  const carEl=$('tb-car');
  carEl.style.display=carName?'inline':'none';
  carEl.textContent=carName||'';
  const ccEl=$('tb-cc');
  const _cc=pfCarClass(d.car_pi, d.car_class);
  if(_cc){
    ccEl.textContent=_cc;
    ccEl.className='cc tb-cc cc-'+_cc;
    ccEl.style.display='inline';
  } else { ccEl.style.display='none'; }
  const piEl=$('tb-pi');
  if(d.car_pi!=null){ piEl.textContent=d.car_pi; piEl.style.display='inline'; }
  else { piEl.style.display='none'; }
  $('tb-drs').style.display=d.drs?'inline':'none';
  $('tb-cmp').textContent=d.tyre_compound||'';

  // track session id and show/hide finish button
  if(d.session_id) state_sid = d.session_id;
  $('btn-finish').style.display = (recv||ended) ? 'inline-block' : 'none';

  // Auto-open confirm modal shortly after race_ended. Short delay (500ms)
  // gives the user a beat to see the dashboard transition before the modal
  // pops; previously this was 5s which felt like a hang. See #32.
  // _foShown guard prevents re-popping after the user closes the modal —
  // state.status='race_ended' lingers for 30s so without the guard every
  // dashboard tick would re-fire openFinish.
  if(!ended) _foShown=false;  // reset for the next race_ended phase

  // Debug mode: speak once when race-end is detected, so you can hear
  // whether detection timing matches what happened on track. Guarded so
  // it fires once per race_ended phase (state lingers ~30s). Web Speech
  // API — no audio assets; silently no-ops if the browser lacks it.
  if(!ended) _spokeOver=false;
  if(ended && d.debug_mode && !_spokeOver){
    _spokeOver=true;
    try{
      const u=new SpeechSynthesisUtterance('I think the race is over');
      speechSynthesis.speak(u);
    }catch(e){}
  }
  if(ended && !$('fo').classList.contains('open') && !_foShown){
    if(!_foAutoTimer) _foAutoTimer=setTimeout(()=>{_foAutoTimer=null;_foShown=true;openFinish();},500);
  } else if(!ended&&_foAutoTimer){
    clearTimeout(_foAutoTimer);_foAutoTimer=null;
  }

  // gear
  const g=d.gear;
  const ge=$('gear');
  ge.textContent=g==null?'—':g===0?'N':g===-1?'R':String(g);
  ge.className='gear-val'+(g===0?' N':g===-1?' R':'');

  // speed
  $('spd').textContent=d.speed_mph!=null?d.speed_mph.toFixed(0):'—';

  // rpm bar
  const rpm=d.rpm||0;
  if(d.engine_max_rpm&&d.engine_max_rpm>2000)_maxRpm=d.engine_max_rpm;
  const rPct=Math.min(100,rpm/_maxRpm*100);
  // RPM moved from horizontal bottom-strip track to a vertical column next to
  // Throttle. Drive height instead of width; use .rpm-vfill (vbar-fill) zones.
  const rf=$('rpm-fill');
  rf.style.height=rPct+'%';
  rf.className='vbar-fill rpm-vfill '+(rPct>=88?'shift':rPct>=75?'hi':rPct>=55?'mid':'lo');
  $('rpm-pct').textContent=rPct>0?Math.round(rPct)+'%':'—';
  $('rpm-num').textContent=rpm?Math.round(rpm).toLocaleString()+' rpm':'—';

  // pedals
  const thr=d.throttle_pct||0,brk=d.brake_pct||0;
  $('thr-b').style.height=thr+'%';
  $('thr-v').textContent=Math.round(thr)+'%';
  $('brk-b').style.height=brk+'%';
  $('brk-v').textContent=Math.round(brk)+'%';
  // flash only while actively receiving — suppress during idle/race_ended
  if(recv&&brk>92) flash('brk-row');

  // slip
  _liveGame=d.game;
  setSlip('srl',d.slip_rl);
  setSlip('srr',d.slip_rr);
  // flash slip panel on oversteer — threshold is game-specific (ACC in m/s, Forza/F1 normalized ratio)
  const _slipAlert=(_liveGame==='acc')?0.6:0.6;
  if(recv&&((d.slip_rl||0)>_slipAlert||(d.slip_rr||0)>_slipAlert)) flash('slip-panel');

  // timing
  $('t-cur').textContent=fmt(d.current_lap_time);
  $('t-best').textContent=fmt(d.best_lap_time_s);
  $('t-last').textContent=fmt(d.last_lap_time_s);
  $('t-lap').textContent=lapLabel(d.lap);

  // Live in-race delta vs this session's best lap (computed server-side per
  // packet from the best-lap distance→time timeline). Null on lap 1 (no
  // reference yet) and outside the lap bounds.
  const dEl=$('t-delta');
  const delta=d.delta_to_best_s;
  if(delta!=null){
    const sign=delta<0?'':'+';
    dEl.textContent=sign+delta.toFixed(2)+'s';
    dEl.className='delta-val '+(delta<-0.01?'ahead':delta>0.01?'behind':'even');
  } else {
    dEl.textContent='—'; dEl.className='delta-val even';
  }

  // race position (current, grid, ± gained vs grid)
  const rp=d.race_position, gp=d.grid_pos;
  $('pos-cur').textContent  = rp ? 'P'+rp : '—';
  $('pos-grid').textContent = gp ? 'P'+gp : '—';
  const pdEl=$('pos-delta');
  if(rp && gp){
    const gained=gp-rp;  // positive = gained positions vs grid
    pdEl.textContent = gained>0 ? '+'+gained : gained<0 ? String(gained) : '0';
    pdEl.className='delta-val '+(gained>0?'ahead':gained<0?'behind':'even');
  } else {
    pdEl.textContent='—'; pdEl.className='delta-val even';
  }

  // tyres
  ['fl','fr','rl','rr'].forEach(c=>{
    const el=$('ty-'+c);
    const t=d['tyre_'+c];
    el.textContent=t!=null?Math.round(t)+'°':'—';
    el.className='tyre-temp '+tyreClass(t);
  });
  const tyCmp=$('ty-cmp');if(tyCmp)tyCmp.textContent=d.tyre_compound||'';

  // udp strip
  const udp=d.udp_received||{},rej=d.udp_rejected||{},rsz=d.last_rejected_size||{};
  $('udp-strip').innerHTML=['forza_motorsport','acc','f1'].map(gm=>{
    const n=udp[gm]||0,r=rej[gm]||0,sz=rsz[gm];
    const c=n>0?'#22c55e33':r>0?'#ef444433':'#1a1a1a';
    return `<span style="color:${c}">${gm.replace('_motorsport','').replace('_',' ')}: ${n}ok${r?' '+r+'rej':''}${sz?' ('+sz+'B)':''}</span>`;
  }).join('<span style="color:var(--color-border-subtle)"> · </span>');
};

es.onerror=()=>{$('dot').className='dot';};

function toggleDebug(){
  _dbgOpen=!_dbgOpen;
  $('dbg').style.display=_dbgOpen?'flex':'none';
  $('dbg-btn').className='bot-btn'+(_dbgOpen?' on':'');
  if(_dbgOpen&&!_dbgEs)startDbg();
  // System-load widget — only poll while the debug panel is visible so we
  // don't burn CPU/network on every dashboard while idle.
  if(_dbgOpen)startSysLoad();
  else stopSysLoad();
}

// ── System load widget (debug panel) ────────────────────────────────────────
let _sysTimer=null;
async function tickSysLoad(){
  try{
    const s=await fetch('/system/load').then(r=>r.json());
    $('sys-cpu').textContent  = s.cpu_pct  != null ? s.cpu_pct + '%' : '—';
    $('sys-load').textContent = s.load     ? s.load.map(v=>v.toFixed(2)).join(' / ') : '—';
    $('sys-mem').textContent  = s.mem      ? (s.mem.used_mb + '/' + s.mem.total_mb + ' MB (' + s.mem.used_pct + '%)') : '—';
    $('sys-temp').textContent = s.cpu_temp_c != null ? s.cpu_temp_c + '°C' : '—';
    $('sys-disk').textContent = s.disk_used_pct != null ? s.disk_used_pct + '%' : '—';
  }catch(e){/* keep the previous values on transient errors */}
}
function startSysLoad(){
  if(_sysTimer)return;
  tickSysLoad();                      // first read primes the CPU-delta calc; UI fills on the second tick
  _sysTimer=setInterval(tickSysLoad, 2000);
}
function stopSysLoad(){
  if(_sysTimer){clearInterval(_sysTimer);_sysTimer=null;}
}
function startDbg(){
  _dbgEs=new EventSource('/debug-stream');
  _dbgEs.onmessage=e=>addDbg(JSON.parse(e.data));
  _dbgEs.onerror=()=>{_dbgEs=null;if(_dbgOpen)setTimeout(startDbg,2000);};
}
function lnColor(l){
  if(l.includes('[ERROR]'))return'#ef4444';
  if(l.includes('[WARNING]')||l.includes('[REJECTED]'))return'#f59e0b';
  if(l.includes('[UDP OK]'))return'#22c55e33';
  return'#1e1e2a';
}
function lnVis(l){
  const f=$('dbg-f').value;
  if(f==='warn')return l.includes('[ERROR]')||l.includes('[WARNING]')||l.includes('[REJECTED]');
  if(f==='udp')return l.includes('[UDP OK]')||l.includes('[REJECTED]');
  return true;
}
function addDbg(line){
  _dbgLines.push(line);if(_dbgLines.length>2000)_dbgLines.shift();
  if(!lnVis(line))return;
  const el=$('dbg-log');
  const d=document.createElement('div');
  d.style.cssText='color:'+lnColor(line)+';border-bottom:1px solid var(--color-border-subtle);padding:1px 0';
  d.textContent=line;el.appendChild(d);
  while(el.children.length>1000)el.removeChild(el.firstChild);
  if($('dbg-as').checked)el.scrollTop=el.scrollHeight;
}
function applyFilter(){
  const el=$('dbg-log');el.innerHTML='';
  _dbgLines.filter(lnVis).slice(-500).forEach(l=>{
    const d=document.createElement('div');
    d.style.cssText='color:'+lnColor(l)+';border-bottom:1px solid var(--color-border-subtle);padding:1px 0';
    d.textContent=l;el.appendChild(d);
  });
  el.scrollTop=el.scrollHeight;
}
function clearDebug(){_dbgLines.length=0;$('dbg-log').innerHTML='';}

// ── Finish Race overlay ───────────────────────────────────────────────────────
let _foSid=null, _foRaceType=null, _foDropLast=false, _foLaps=[], _foClosed=false;
let _foTrackOrdinal=null, _foAutoTimer=null;
let _foWeather=null, _foTyre=null;
// True after the modal has been auto-opened (or manually opened) for the
// current race_ended phase. Resets when status leaves race_ended (on next
// race or after the 30s _clear_race_ended timeout). Prevents the modal from
// re-popping every dashboard tick after the user has saved or skipped.
let _foShown=false;
let _spokeOver=false;  // debug-mode "race is over" announced this phase

// Each chip-group selector clears chips inside its own .fo-section so a Type
// pick doesn't accidentally clear Weather/Tyres (they all share .type-chip).
function _foSelChip(el){
  const section=el.closest('.fo-section');
  if(section)section.querySelectorAll('.type-chip').forEach(c=>c.classList.remove('sel'));
  el.classList.add('sel');
}
function selType(el){_foSelChip(el);_foRaceType=el.dataset.val;}
function selWeather(el){_foSelChip(el);_foWeather=el.dataset.val;}
function selTyre(el){
  // Tyre is optional — clicking the active chip toggles it off (matches
  // session-detail behavior).
  if(el.classList.contains('sel')){el.classList.remove('sel');_foTyre=null;return;}
  _foSelChip(el);_foTyre=el.dataset.val;
}

async function openFinish(editSid){
  if(_foAutoTimer){clearTimeout(_foAutoTimer);_foAutoTimer=null;}
  // Mark that the modal was shown for this race_ended phase so the
  // dashboard tick handler doesn't auto-open it again after the user
  // closes it. See _foShown comment at top of the file.
  _foShown=true;

  // Optimistic UX: pop the modal IMMEDIATELY with a loading state so the
  // button feels responsive. The /finish POST blocks on synchronous DB +
  // file writes; we used to await it before opening, which made the click
  // feel multi-second slow. See #32.
  $('fo-title').textContent = 'Finishing race…';
  $('fo-sub').textContent   = 'Saving session…';
  $('fo-stats').style.display = 'none';
  $('fo').classList.add('open');

  let sid = editSid || null;
  if(!editSid){
    // Close active session
    const res = await fetch('/finish',{method:'POST'});
    const closed = await res.json().catch(()=>({}));
    if(closed.closed&&closed.closed.length) sid=closed.closed[0];
    if(!sid){
      const st = await fetch('/status').then(r=>r.json());
      sid = state_sid || st.session_id;
    }
  }
  _foSid=sid; _foRaceType=null; _foDropLast=false; _foClosed=false; _foTrackOrdinal=null;
  _foWeather=null; _foTyre=null;
  // Reset chip selections from a previous open before re-render.
  document.querySelectorAll('#fo .type-chip').forEach(c=>c.classList.remove('sel'));
  if(!_foSid){
    // Couldn't recover a session id — back out cleanly so the user isn't
    // stuck on a "Finishing race…" placeholder.
    $('fo').classList.remove('open');
    return;
  }

  try {
    // Load session metadata + track list
    const cd = await fetch('/sessions/confirm-data?id='+encodeURIComponent(_foSid)).then(r=>r.json());
    const cur = cd.session;
    if(!cur) return;
    _foSid = cur.session_id||_foSid;
    _foTrackOrdinal = cd.track_ordinal;

    // Load laps
    const ld = await fetch('/sessions/session/data?id='+encodeURIComponent(_foSid)).then(r=>r.json()).catch(()=>({}));
    _foLaps = ld.laps||[];

    // Header
    const track = cur.track&&cur.track!=='unknown' ? cur.track : null;
    $('fo-title').textContent = track||'Session Complete';
    const badge=$('fo-game-badge');
    if(cur.game){badge.textContent=(cur.game||'').replace(/_/g,' ').toUpperCase();badge.style.display='inline';}
    else badge.style.display='none';
    $('fo-sub').textContent = cur.started_at
      ? new Date(cur.started_at).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
      : '—';

    // Stats row
    const validLaps=_foLaps.filter(l=>l.lap_time_s);
    if(validLaps.length){
      const best=Math.min(...validLaps.map(l=>l.lap_time_s));
      $('fo-stat-laps').textContent=validLaps.length;
      $('fo-stat-best').textContent=fmt(best);
      $('fo-stats').style.display='flex';
    } else {
      $('fo-stats').style.display='none';
    }

    // Track dropdown
    const sel=$('fo-track');
    sel.innerHTML='<option value="">— Unknown —</option>';
    (cd.track_list||[]).forEach(t=>{
      const o=document.createElement('option');
      o.value=t;o.textContent=t;
      if(t===cur.track)o.selected=true;
      sel.appendChild(o);
    });
    // If track is an unidentified ordinal, add as a selectable option too
    if(cur.track&&cur.track.startsWith('Track #')&&!sel.value){
      const o=document.createElement('option');
      o.value=cur.track;o.textContent=cur.track+' (unidentified)';o.selected=true;
      sel.insertBefore(o,sel.options[1]);
    }

    // Car input
    $('fo-car').value=cur.car&&cur.car!=='unknown'?cur.car:'';

    // Pre-select race_type / weather / tyres if the session already has them.
    // CSS selectors scoped to each .fo-section so the same data-val (e.g.
    // "Wet" appears for both Weather and Tyres) doesn't cross-fire.
    const sections=$('fo').querySelectorAll('.fo-section');
    function _preselect(handler, val){
      if(!val) return;
      for(const sec of sections){
        const chip=sec.querySelector(`.type-chip[data-val="${val}"]`);
        if(chip && handler.name === 'selType' && sec.querySelector('[onclick*="selType"]')){handler(chip);break;}
        if(chip && handler.name === 'selWeather' && sec.querySelector('[onclick*="selWeather"]')){handler(chip);break;}
        if(chip && handler.name === 'selTyre' && sec.querySelector('[onclick*="selTyre"]')){handler(chip);break;}
      }
    }
    _preselect(selType, cur.race_type);
    _preselect(selWeather, cur.weather_condition);
    _preselect(selTyre, cur.tyre_compound);
    renderFoLaps();
  } catch(e){
    // Don't strand the user on a "Finishing race…" placeholder if any of the
    // session/data fetches failed. Surface the error in the title and let
    // them dismiss with Skip.
    console.error(e);
    $('fo-title').textContent = 'Could not load session';
    $('fo-sub').textContent   = String(e && e.message || e);
    return;
  }
  // Modal is already open from the optimistic step at the top of openFinish.
}

function renderFoLaps(){
  const validTimes=_foLaps.filter(l=>l.lap_time_s).map(l=>l.lap_time_s);
  const best=validTimes.length?Math.min(...validTimes):null;
  const lastIdx=_foLaps.length-1;
  $('fo-laps').innerHTML=_foLaps.map((lap,i)=>{
    const t=lap.lap_time_s;
    const isLast=i===lastIdx;
    const isBest=t&&t===best;
    const isPartial=isLast&&(!t||_foDropLast);
    const timeStr=t?fmt(t):'partial';
    const delBtn=isLast
      ?`<button class="fo-lap-del${_foDropLast?' undone':''}" onclick="toggleDropLast()">${_foDropLast?'Restore':'Delete'}</button>`
      :'';
    return `<div class="fo-lap${isPartial?' partial':''}">
      <span class="fo-lap-num">${lapLabel(lap.lap_number)}</span>
      <span class="fo-lap-time${isBest&&!_foDropLast?' best':''}">${timeStr}</span>
      ${isPartial&&!_foDropLast?'<span class="fo-lap-badge">PARTIAL</span>':''}
      ${delBtn}
    </div>`;
  }).join('');
}

function toggleDropLast(){
  _foDropLast=!_foDropLast;
  renderFoLaps();
}

async function saveFinish(){
  if(!_foSid) return;
  const body={id:_foSid};
  if(_foRaceType) body.race_type=_foRaceType;
  if(_foDropLast) body.drop_last_lap=true;
  const selTrack=$('fo-track').value;
  if(selTrack&&!selTrack.startsWith('Track #')) body.track=selTrack;
  const carVal=$('fo-car').value.trim();
  if(carVal) body.car=carVal;
  // Always send weather + tyre (empty string clears, matches session-detail flow).
  body.weather_condition=_foWeather||'';
  body.tyre_compound=_foTyre||'';
  // Learn the ordinal if user identified an unknown track
  if(_foTrackOrdinal&&selTrack&&!selTrack.startsWith('Track #')){
    body.learned_ordinal={ordinal:_foTrackOrdinal,game:'forza_motorsport',track_name:selTrack};
  }
  await fetch('/sessions/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  closeFinish();
}

function closeFinish(){
  $('fo').classList.remove('open');
  if(_foAutoTimer){clearTimeout(_foAutoTimer);_foAutoTimer=null;}
}
