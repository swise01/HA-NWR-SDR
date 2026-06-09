// ── State ──────────────────────────────────────────────────────────────────
// Forza UDP lap_number is 0-indexed (race lap 1 = lap_number 0). Match
// Forza's on-screen 1-indexed display when rendering. ACC is parked.
const lapLabel = n => 'L' + (Number(n) + 1);
const _id=new URLSearchParams(location.search).get('id')||'';
const _sgame=new URLSearchParams(location.search).get('game')||'';
const _strack=new URLSearchParams(location.search).get('track')||'';
let _sess=null,_laps=[];
let _lapSamples={};   // {lapNum: [sample,...]}
let _refSamples=null,_refMeta=null;
let _selectedLaps=[];  // ordered, max 4
let _primaryLap=null;
let _refType='best_lap';
let _refSid=null,_refLapNum=null;  // for cross_session reference picks
let _prevRefType='best_lap';       // restore target if cross-session picker is cancelled
let _xMode='distance';
let _zoom=[0,1];
let _maxT=1;
let _dragging=false,_dragX0=0,_dragY0=0,_dragMoved=false;
let _spaceDown=false,_panning=false,_panX0=0,_panZoom0=[0,1];
let _tmCx=null,_tmCy=null;
// Click-to-lock cursor on the charts/track-map. When locked, the vertical
// line + tooltip + map dot stay at the locked x-fraction even as the mouse
// moves away. Click again on a chart (or hit Esc) to unlock. ←/→ to nudge.
let _cursorLocked=false,_cursorXFrac=null,_cursorTipX=null,_cursorTipY=null;
const LAP_COLORS=['#4a9aef','#22c55e','#f59e0b','#a855f7'];
const REF_COL='#e5e7eb';  // bright neutral so the dashed reference line reads on a dark bg
const W=1000;
const $=id=>document.getElementById(id);
// True when a selected lap IS the active reference lap (so its delta is 0 by
// definition). Only matters for references that map to a real lap in the
// CURRENT session — theoretical is a virtual composite, cross_session is
// always a different session.
function isRefLap(lapNum){
  if(_refType==='best_lap'){
    if(!_refMeta||!_refMeta.best_lap)return false;
    if(_refMeta.best_lap.session_id!==_id)return false;
    return _refMeta.best_lap.lap_number===lapNum;
  }
  if(_refType==='last_lap'){
    const valid=_laps.filter(l=>l.lap_time_s);
    if(!valid.length)return false;
    return valid[valid.length-1].lap_number===lapNum;
  }
  return false;
}
// ── X value of a sample (distance or time-normalised) ────────────────────
function xv(s){return _xMode==='distance'?s.distance_norm:(s.t/_maxT);}
// ── Interpolate field at normalised X position ────────────────────────────
function interpAt(samples,pos,field){
  if(!samples||!samples.length)return 0;
  let lo=0,hi=samples.length-1;
  while(lo<hi-1){const mid=(lo+hi)>>1;if(xv(samples[mid])<=pos)lo=mid;else hi=mid;}
  const a=samples[lo],b=samples[hi];
  const dn=xv(b)-xv(a);
  if(dn<1e-9)return a[field]??0;
  return (a[field]??0)+((pos-xv(a))/dn)*((b[field]??0)-(a[field]??0));
}
// ── Map sample X to SVG x coordinate (applies zoom) ──────────────────────
function sX(s){return((xv(s)-_zoom[0])/(_zoom[1]-_zoom[0]))*W;}
function normToSX(pos){return((pos-_zoom[0])/(_zoom[1]-_zoom[0]))*W;}
// ── Filter samples to zoom window (+margin for clean edges) ──────────────
function zs(samples){
  if(!samples)return[];
  const lo=_zoom[0]-0.002,hi=_zoom[1]+0.002;
  return samples.filter(s=>{const v=xv(s);return v>=lo&&v<=hi;});
}
// ── Delta builder ─────────────────────────────────────────────────────────
function buildDelta(lapS,refS,N=500){
  const out=[];
  const lo=_zoom[0],hi=_zoom[1];
  for(let i=0;i<=N;i++){
    const pos=lo+i/N*(hi-lo);
    out.push({pos,d:interpAt(lapS,pos,'t')-interpAt(refS,pos,'t')});
  }
  return out;
}
// Renders cumulative DELTA. Accepts an array of laps: [{ln, col, d:[{pos,d},...]}, ...]
// Single-lap: sign-colored fill polygons (green=faster, red=slower) — most informative.
// Multi-lap: per-lap colored polylines.
function deltaSVG(lapDeltas,H=32){
  const zY=H/2;
  let maxA=0.001;
  lapDeltas.forEach(({d})=>d.forEach(p=>{if(Math.abs(p.d)>maxA)maxA=Math.abs(p.d);}));
  const sc=(H/2-4)/maxA;
  let body='';
  if(lapDeltas.length===1){
    const delta=lapDeltas[0].d;
    const pts=delta.map(p=>({x:normToSX(p.pos).toFixed(1),y:(zY-p.d*sc).toFixed(1)}));
    let segs=[],cur=null;
    for(let i=0;i<delta.length;i++){
      const sg=delta[i].d<0?'g':'r';
      if(!cur||cur.sg!==sg){if(cur)segs.push(cur);cur={sg,idx:[i]};}
      else cur.idx.push(i);
    }
    if(cur)segs.push(cur);
    body=segs.map(s=>{
      const fc=s.sg==='g'?'#22c55e':'#ef4444';
      const tr=s.idx.map(i=>`${pts[i].x},${pts[i].y}`);
      const cl=[`${pts[s.idx[s.idx.length-1]].x},${zY}`,`${pts[s.idx[0]].x},${zY}`];
      return`<polygon points="${[...tr,...cl].join(' ')}" fill="${fc}55" stroke="${fc}" stroke-width="1.2" stroke-linejoin="round"/>`;
    }).join('');
  }else{
    body=lapDeltas.map(({col,d})=>{
      const pts=d.map(p=>`${normToSX(p.pos).toFixed(1)},${(zY-p.d*sc).toFixed(1)}`).join(' ');
      return`<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5" opacity=".9"/>`;
    }).join('');
  }
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">
    <line x1="0" y1="${zY}" x2="${W}" y2="${zY}" stroke="#1e1e1e" stroke-width="1"/>
    ${secLine(1/3,H)}${secLine(2/3,H)}${body}
    ${secLabel(0,'S1',H)}${secLabel(1/3,'S2',H)}${secLabel(2/3,'S3',H)}
  </svg>`;
}
// ── Local minima detection ────────────────────────────────────────────────
function localMins(samples,field,minDrop=8){
  const sl=zs(samples);const out=[];
  for(let i=3;i<sl.length-3;i++){
    const v=sl[i][field]??0;
    const ctx=[sl[i-3][field]??0,sl[i-2][field]??0,sl[i-1][field]??0,sl[i+1][field]??0,sl[i+2][field]??0,sl[i+3][field]??0];
    if(ctx.every(c=>v<=c)&&Math.max(...ctx.slice(0,3))-v>=minDrop)
      out.push({i,v,x:sX(sl[i]).toFixed(1),y:null});
  }
  return out.filter((m,i)=>i===0||(xv(sl[m.i])-xv(sl[out[i-1].i]))>0.04);
}
function localMaxes(samples,field,thresh){
  const sl=zs(samples);const out=[];
  for(let i=2;i<sl.length-2;i++){
    const v=sl[i][field]??0;
    if(v<thresh)continue;
    if(v>=(sl[i-2][field]??0)&&v>=(sl[i-1][field]??0)&&v>=(sl[i+1][field]??0)&&v>=(sl[i+2][field]??0))
      out.push({i,v,x:sX(sl[i]).toFixed(1)});
  }
  return out.filter((m,i)=>i===0||(xv(sl[m.i])-xv(sl[out[i-1].i]))>0.04);
}
// ── Panel builder ─────────────────────────────────────────────────────────
// Per-chart mini-axis row — repeats 0/25/50/75/100% under every chart so
// users don't have to mentally project the shared bottom axis up to each
// chart. Issue #12 polish bundle.
const _PX_AXIS = `<div class="px-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>`;
function setPanel(id,label,svgHtml,show,withRef){
  const p=$(id);
  if(!show){p.style.display='none';return;}
  p.style.display='';
  const refTag=withRef&&_refSamples?`<span class="ref-tag">REF · ${refLabel()}</span>`:'';
  p.innerHTML=`<div class="panel-lbl-row"><span class="p-lbl">${label}</span>${refTag}</div>
<div class="panel-svg-wrap" data-panel="${id}"><div class="px-line"></div>${svgHtml}</div>${_PX_AXIS}`;
}
function refLabel(){
  if(_refType==='best_lap')return 'My Best';
  if(_refType==='theoretical')return 'Theoretical';
  if(_refType==='last_lap')return 'Last Lap';
  if(_refType==='cross_session')return 'Cross-session';
  return 'Reference';
}
// ── Individual panel SVG builders ─────────────────────────────────────────
function speedSVG(){
  const H=140;
  const allS=Object.values(_lapSamples).filter(Boolean);
  let[mn,mx]=autoRange([...allS,_refSamples?_refSamples:[]],'speed_mph');mn=Math.max(0,mn);
  const yr=mx-mn||1;
  let c=`${secLine(1/3,H)}${secLine(2/3,H)}${secLabel(0,'S1',H)}${secLabel(1/3,'S2',H)}${secLabel(2/3,'S3',H)}`;
  if(_refSamples)c+=`<path d="${linePts(_refSamples,'speed_mph',H,mn,mx)}" fill="none" stroke="${REF_COL}" stroke-width="1" stroke-dasharray="7,4" opacity=".75"/>`;
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?1:.4;
    c+=`<path d="${linePts(s,'speed_mph',H,mn,mx)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}"/>`;
    if(ln===_primaryLap){
      const mins=localMins(s,'speed_mph');
      const sl=zs(s);
      mins.forEach(m=>{
        const ss=sl[m.i];if(!ss)return;
        const x=parseFloat(sX(ss).toFixed(1));
        const y=H-((ss.speed_mph-mn)/yr*H);
        // Triangle tip points down to the minimum; base sits 10px above
        c+=`<polygon points="${x},${y.toFixed(1)} ${(x-5).toFixed(1)},${(y-10).toFixed(1)} ${(x+5).toFixed(1)},${(y-10).toFixed(1)}" fill="${col}" opacity=".8"/>
        <text x="${x}" y="${(y-13).toFixed(1)}" fill="${col}" font-size="14" text-anchor="middle" font-family="monospace" opacity=".9">${Math.round(ss.speed_mph)}</text>`;
      });
    }
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function throttleSVG(){
  const H=100;
  const y50=(H-50/100*H).toFixed(1),y70=(H-70/100*H).toFixed(1);
  let c=`${secLine(1/3,H)}${secLine(2/3,H)}
    <rect x="0" y="${y70}" width="${W}" height="${(parseFloat(y50)-parseFloat(y70)).toFixed(1)}" fill="#f59e0b1f"/>`;
  if(_refSamples)c+=`<path d="${linePts(_refSamples,'throttle_pct',H,0,100)}" fill="none" stroke="${REF_COL}" stroke-width="1" stroke-dasharray="7,4" opacity=".75"/>`;
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?1:.4;
    if(ln===_primaryLap)c+=`<path d="${fillPts(s,'throttle_pct',H,0,100)}" fill="${col}1a" stroke="none"/>`;
    c+=`<path d="${linePts(s,'throttle_pct',H,0,100)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}"/>`;
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function brakeSVG(){
  const H=80;
  let c=`${secLine(1/3,H)}${secLine(2/3,H)}`;
  if(_refSamples)c+=`<path d="${linePts(_refSamples,'brake_pct',H,0,100)}" fill="none" stroke="${REF_COL}" stroke-width="1" stroke-dasharray="7,4" opacity=".75"/>`;
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?1:.4;
    if(ln===_primaryLap)c+=`<path d="${fillPts(s,'brake_pct',H,0,100)}" fill="#ef44441a" stroke="none"/>`;
    c+=`<path d="${linePts(s,'brake_pct',H,0,100)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}"/>`;
    if(ln===_primaryLap){
      const peaks=localMaxes(s,'brake_pct',75);
      const sl=zs(s);
      peaks.forEach(pk=>{
        const ss=sl[pk.i];if(!ss)return;
        const x=sX(ss).toFixed(1),y=(H-pk.v/100*H).toFixed(1);
        c+=`<circle cx="${x}" cy="${y}" r="3.5" fill="${col}" opacity=".8"/>`;
      });
    }
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function gearSVG(){
  const H=60,gM=8;
  let c=`${secLine(1/3,H)}${secLine(2/3,H)}`;
  for(let g=1;g<=gM;g++){
    const y1=(H-(g/gM)*H).toFixed(1),y2=(H-((g-1)/gM)*H).toFixed(1);
    if(g%2===0)c+=`<rect x="0" y="${y1}" width="${W}" height="${(parseFloat(y2)-parseFloat(y1)).toFixed(1)}" fill="#ffffff03"/>`;
  }
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?.9:.3;
    c+=`<path d="${stepPts(s,'gear',H,0,gM)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}" stroke-linejoin="miter"/>`;
  });
  for(let g=1;g<=gM;g++)c+=`<text x="5" y="${(H-((g-.5)/gM)*H+5).toFixed(1)}" fill="#2a2a2a" font-size="17" font-family="monospace">${g}</text>`;
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function steerSVG(){
  const H=60;
  const allS=Object.values(_lapSamples).filter(Boolean);
  const[mn,mx]=autoRange(allS,'steer');
  const zeroY=(H-((0-mn)/(mx-mn||1))*H).toFixed(1);
  let c=`<line x1="0" y1="${zeroY}" x2="${W}" y2="${zeroY}" stroke="#222" stroke-width="1"/>
    ${secLine(1/3,H)}${secLine(2/3,H)}`;
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?.9:.3;
    c+=`<path d="${linePts(s,'steer',H,mn,mx)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}"/>`;
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function slipSVG(){
  const H=100,mx=1;
  const y10=(H-0.1*H).toFixed(1),y30=(H-0.3*H).toFixed(1);
  let c=`<rect x="0" y="0" width="${W}" height="${y30}" fill="#ef44440a"/>
    <rect x="0" y="${y30}" width="${W}" height="${(parseFloat(y10)-parseFloat(y30)).toFixed(1)}" fill="#f59e0b0a"/>
    <rect x="0" y="${y10}" width="${W}" height="${(H-parseFloat(y10)).toFixed(1)}" fill="#22c55e0a"/>
    <line x1="0" y1="${y10}" x2="${W}" y2="${y10}" stroke="#22c55e1a" stroke-width="1"/>
    <line x1="0" y1="${y30}" x2="${W}" y2="${y30}" stroke="#f59e0b1a" stroke-width="1"/>
    ${secLine(1/3,H)}${secLine(2/3,H)}
    <text x="4" y="${H-4}" fill="#22c55e" font-size="10" text-anchor="start" font-family="monospace">Optimal</text>
    <text x="4" y="${((parseFloat(y30)+parseFloat(y10))/2+5).toFixed(1)}" fill="#f59e0b" font-size="10" text-anchor="start" font-family="monospace">Managed</text>
    <text x="4" y="${(parseFloat(y30)/2+5).toFixed(1)}" fill="#ef4444" font-size="10" text-anchor="start" font-family="monospace">Excess</text>`;
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const col=LAP_COLORS[ci],op=ln===_primaryLap?1:.35;
    c+=`<path d="${linePts(s,'slip_rl',H,0,mx)}" fill="none" stroke="${col}" stroke-width="${ln===_primaryLap?1.5:1}" opacity="${op}"/>`;
    c+=`<path d="${linePts(s,'slip_rr',H,0,mx)}" fill="none" stroke="#93c5fd" stroke-width="${ln===_primaryLap?1.5:1}" stroke-dasharray="5,3" opacity="${op*.7}"/>`;
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
function tyreSVG(){
  const allS=Object.values(_lapSamples).filter(Boolean);
  const hasTyre=allS.some(ss=>ss.some(s=>s.tyre_fl!=null));
  if(!hasTyre)return null;
  const H=80;
  let[mn,mx]=autoRange(allS,'tyre_fl');
  if(!isFinite(mn)||mx-mn<20){mn=Math.min(isFinite(mn)?mn:160,160);mx=Math.max(isFinite(mx)?mx:220,220);}
  const yr=mx-mn||1;
  const yOL=(H-((180-mn)/yr*H)).toFixed(1),yOH=(H-((200-mn)/yr*H)).toFixed(1);
  let c=`<rect x="0" y="${yOH}" width="${W}" height="${(parseFloat(yOL)-parseFloat(yOH)).toFixed(1)}" fill="#22c55e0a"/>
    <line x1="0" y1="${yOH}" x2="${W}" y2="${yOH}" stroke="#22c55e1a" stroke-width="1"/>
    <line x1="0" y1="${yOL}" x2="${W}" y2="${yOL}" stroke="#22c55e1a" stroke-width="1"/>
    ${secLine(1/3,H)}${secLine(2/3,H)}`;
  const tCols=['#ef4444','#4a9aef','#f59e0b','#22c55e'];
  const corners=['fl','fr','rl','rr'];
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const op=ln===_primaryLap?1:.35;
    corners.forEach((cr,ti)=>{
      const p=linePts(s,`tyre_${cr}`,H,mn,mx);
      if(p)c+=`<path d="${p}" fill="none" stroke="${tCols[ti]}" stroke-width="1.5" opacity="${op}"/>`;
    });
  });
  return`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">${c}</svg>`;
}
// ── Sector time helper ─────────────────────────────────────────────────────
function secTime(samples,lo,hi){
  if(!samples||!samples.length)return null;
  const tLo=lo<=0?samples[0].t:interpAt(samples,lo,'t');
  const tHi=hi>=1?samples[samples.length-1].t:interpAt(samples,hi,'t');
  const dt=tHi-tLo;return dt>0?dt:null;
}
// ── Sector header ─────────────────────────────────────────────────────────
function renderSectorHdr(){
  const lapEntries=_selectedLaps.map(ln=>({ln,s:_lapSamples[ln],col:LAP_COLORS[_selectedLaps.indexOf(ln)],lbl:lapLabel(ln),isRef:isRefLap(ln)}));
  const nonRefCount=lapEntries.filter(l=>!l.isRef).length;
  const showDelta=!!_refSamples&&nonRefCount>0;
  const secs=[[0,1/3,'S1'],[1/3,2/3,'S2'],[2/3,1,'S3']];
  const refTimes=_refSamples?secs.map(([lo,hi])=>secTime(_refSamples,lo,hi)):null;
  const lapTimes=secs.map(([lo,hi,nm])=>{
    const ts=lapEntries.map(l=>secTime(l.s,lo,hi));
    const best=Math.min(...ts.filter(t=>t!=null));
    return{nm,ts,best};
  });
  let html=`<div class="s-hdr-row"><span class="s-row-lbl"></span>`;
  lapEntries.forEach(l=>{
    html+=`<span class="s-cell-hd" style="color:${l.col}">${l.lbl}</span>`;
    if(showDelta)html+=`<span class="s-cell-hd s-cell-d" style="color:${l.col}">Δ</span>`;
  });
  html+='</div>';
  lapTimes.forEach(({nm,ts,best},si)=>{
    html+=`<div class="s-hdr-row"><span class="s-row-lbl">${nm}</span>`;
    ts.forEach((t,i)=>{
      const isBest=t!=null&&Math.abs(t-best)<0.001;
      html+=`<span class="s-cell${isBest?' best':''}" style="color:${lapEntries[i].col}">${t!=null?fmtLap(t):'—'}</span>`;
      if(showDelta){
        const rt=refTimes?refTimes[si]:null;
        if(rt!=null&&t!=null){
          const d=t-rt;
          if(Math.abs(d)<0.0005){
            html+=`<span class="s-cell s-cell-d" style="color:${REF_COL}">0.000</span>`;
          }else{
            const sign=d<0?'−':'+';
            const cls=d<0?'delta-neg':'delta-pos';
            html+=`<span class="s-cell s-cell-d ${cls}">${sign}${Math.abs(d).toFixed(3)}</span>`;
          }
        }else{
          html+=`<span class="s-cell s-cell-d" style="color:${REF_COL}">—</span>`;
        }
      }
    });
    html+='</div>';
  });
  $('sector-hdr').innerHTML=html;
}
// ── Lap summary bars ──────────────────────────────────────────────────────
function renderLapSummaries(){
  let html='';
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];
    const lap=_laps.find(l=>l.lap_number===ln)||{};
    const col=LAP_COLORS[ci];
    const s1=secTime(s,0,1/3),s2=secTime(s,1/3,2/3),s3=secTime(s,2/3,1);
    let dHtml='';
    if(_refSamples&&s){
      const delta=interpAt(s,1,'t')-interpAt(_refSamples,1,'t');
      const sign=delta<0?'−':'+';
      dHtml=`<span class="lsb-d ${delta<0?'delta-neg':'delta-pos'}">${sign}${Math.abs(delta).toFixed(3)}s ${delta<0?'▲':'▼'}</span>`;
    }
    let slipHtml='';
    if(s){
      const slips=s.map(ss=>Math.max(ss.slip_rl??0,ss.slip_rr??0));
      if(slips.length){
        const avg=slips.reduce((a,b)=>a+b,0)/slips.length;
        const peak=Math.max(...slips);
        const pct=slips.filter(v=>v>0.1).length/slips.length*100;
        slipHtml=`Sl avg:${avg.toFixed(3)} pk:${peak.toFixed(3)} &gt;0.1:${pct.toFixed(1)}%`;
      }
    }
    html+=`<div class="lap-sum-bar" style="border-color:${col}">
      <span class="lsb-l" style="color:${col}">LAP ${ln + 1}</span>
      <span class="lsb-t" style="color:${col}">${fmtLap(lap.lap_time_s)}</span>
      <span class="lsb-s">S1 ${s1!=null?fmtLap(s1):'—'} &nbsp;S2 ${s2!=null?fmtLap(s2):'—'} &nbsp;S3 ${s3!=null?fmtLap(s3):'—'}</span>
      ${dHtml}<span class="lsb-slip" title="Tyre slip: max(rear-left, rear-right) per packet&#10;avg = mean across the lap&#10;pk = peak (max) value&#10;&gt;0.1 = % of lap above the 0.1 slip threshold (loose grip)">${slipHtml}</span>
    </div>`;
  });
  $('lap-summaries').innerHTML=html;
}
// ── Track map ─────────────────────────────────────────────────────────────
function renderTrackMap(){
  const s=_lapSamples[_primaryLap];
  if(!s||!s.some(ss=>ss.px!=null)){$('track-map-wrap').style.display='none';return;}
  if(!s.some(ss=>Math.abs(ss.px??0)>0.1||Math.abs(ss.py??0)>0.1||Math.abs(ss.pz??0)>0.1)){$('track-map-wrap').style.display='none';return;}
  $('track-map-wrap').style.display='';
  const hasPz=s.some(ss=>ss.pz!=null);
  const xz=hasPz?ss=>ss.pz:ss=>ss.py??0;
  const xs=s.map(ss=>ss.px),zs2=s.map(xz);
  const spds=s.map(ss=>ss.speed_mph??0);
  const mnX=Math.min(...xs),mxX=Math.max(...xs);
  const mnZ=Math.min(...zs2),mxZ=Math.max(...zs2);
  const mnS=Math.min(...spds),mxS=Math.max(...spds);
  // viewBox sized to the track's own aspect ratio so the SVG fills its
  // container with the shape (vs. letterboxing inside a fixed 900×260
  // rectangle). Cap aspect so a long thin track like Le Mans doesn't
  // collapse the column to a sliver. pd is padding inside the viewBox.
  const pd=24;
  const scX=(mxX-mnX)||1,scZ=(mxZ-mnZ)||1;
  const trackAspect=Math.max(0.5,Math.min(2.5,scX/scZ));
  const TW=trackAspect>=1?600:Math.round(600*trackAspect);
  const TH=trackAspect>=1?Math.round(600/trackAspect):600;
  _tmTW=TW;_tmTH=TH;
  const sc=Math.min((TW-pd*2)/scX,(TH-pd*2)/scZ);
  const offX=(TW-(mxX-mnX)*sc)/2,offZ=(TH-(mxZ-mnZ)*sc)/2;
  const cx=x=>offX+(x-mnX)*sc;
  const cy=z=>TH-offZ-(z-mnZ)*sc;
  _tmCx=cx;_tmCy=cy;_tmHasPz=hasPz;_tmSamples=s;
  let segs='';
  for(let i=1;i<s.length;i++){
    const x1=cx(s[i-1].px).toFixed(1),y1=cy(xz(s[i-1])).toFixed(1);
    const x2=cx(s[i].px).toFixed(1),y2=cy(xz(s[i])).toFixed(1);
    segs+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${spdRgb(spds[i],mnS,mxS)}" stroke-width="3" stroke-linecap="round"/>`;
  }
  const ix=cx(s[0].px).toFixed(1),iy=cy(xz(s[0])).toFixed(1);
  $('track-map-inner').innerHTML=`<svg viewBox="0 0 ${TW} ${TH}" width="100%" style="display:block">
    ${segs}
    <circle id="tmap-dot" cx="${ix}" cy="${iy}" r="7" fill="#fff" stroke="rgba(0,0,0,.6)" stroke-width="1.5" opacity=".9"/>
  </svg>`;
}
let _tmHasPz=false,_tmSamples=null,_tmTW=600,_tmTH=600;
function updateTrackDot(pos){
  const dot=$('tmap-dot');
  if(!dot||!_tmCx||!_tmSamples)return;
  const idx=Math.min(_tmSamples.length-1,Math.max(0,Math.round(pos*(_tmSamples.length-1))));
  const ss=_tmSamples[idx];
  if(ss&&ss.px!=null){
    const z=_tmHasPz?(ss.pz??0):(ss.py??0);
    dot.setAttribute('cx',_tmCx(ss.px).toFixed(1));
    dot.setAttribute('cy',_tmCy(z).toFixed(1));
  }
}
// ── Main render ───────────────────────────────────────────────────────────
function renderAll(){
  // Empty state: no laps selected → hide everything and show a hint.
  const empty=$('panels-empty');
  const allPanelIds=['panel-delta','panel-speed','panel-throttle','panel-brake','panel-gear','panel-steer','panel-slip','panel-tyre'];
  if(!_primaryLap||!_lapSamples[_primaryLap]){
    if(empty)empty.style.display='';
    allPanelIds.forEach(id=>{const p=$(id);if(p)p.style.display='none';});
    const tm=$('track-map-wrap');if(tm)tm.style.display='none';
    hideHud();
    return;
  }
  if(empty)empty.style.display='none';
  showHud(); resetHud();
  // Delta panel only renders when a reference is selected AND a non-reference lap is also selected.
  let deltaHtml='',showDeltaPanel=false;
  if(_refSamples){
    const nonRefLaps=_selectedLaps.filter(ln=>_lapSamples[ln]&&!isRefLap(ln));
    if(nonRefLaps.length>0){
      const lapDeltas=nonRefLaps.map(ln=>({
        ln,
        col:LAP_COLORS[_selectedLaps.indexOf(ln)],
        d:buildDelta(_lapSamples[ln],_refSamples)
      }));
      deltaHtml=deltaSVG(lapDeltas);
      showDeltaPanel=true;
    }
  }
  setPanel('panel-delta','DELTA — CUMULATIVE TIME VS REFERENCE  (GREEN=FASTER · RED=SLOWER)',deltaHtml,showDeltaPanel,true);
  setPanel('panel-speed','SPEED mph — ▽ corner minimum speed',speedSVG(),$('ch-speed').checked,true);
  setPanel('panel-throttle','THROTTLE % — amber band = 50-70% dwell zone',throttleSVG(),$('ch-throttle').checked,true);
  setPanel('panel-brake','BRAKE % — ● peak points',brakeSVG(),$('ch-brake').checked,true);
  setPanel('panel-gear','GEAR',gearSVG(),$('ch-gear').checked);
  setPanel('panel-steer','STEERING',steerSVG(),$('ch-steer').checked);
  setPanel('panel-slip','SLIP RL (solid) / RR (dashed)',slipSVG(),$('ch-slip').checked);
  const tSVG=tyreSVG();
  setPanel('panel-tyre','TYRE TEMPS °F — green band = optimal 180-200°F',tSVG||'',$('ch-tyre').checked&&!!tSVG);
  renderSectorHdr();
  renderLapSummaries();
  renderTrackMap();
  setupInteraction();
}
// ── Crosshair, tooltip, zoom ───────────────────────────────────────────────
// Render the cursor (vertical line, tooltip, track-map dot) at a given
// x-fraction of the zoom window. When mouseEvent is null (e.g. cursor is
// locked), the tooltip stays at its last on-screen position.
function paintCursor(xFrac, mouseEvent){
  const area=$('charts-area');
  const tip=$('tele-tip');
  area.querySelectorAll('.px-line').forEach(l=>{
    l.style.left=(xFrac*100)+'%';
    l.style.display='';
    l.classList.toggle('locked', _cursorLocked);
  });
  const pos=_zoom[0]+xFrac*(_zoom[1]-_zoom[0]);
  updateTrackDot(pos);
  const lines=[];
  _selectedLaps.forEach((ln,ci)=>{
    const s=_lapSamples[ln];if(!s)return;
    const sp=(interpAt(s,pos,'speed_mph')||0).toFixed(0);
    const th=(interpAt(s,pos,'throttle_pct')||0).toFixed(0);
    const br=(interpAt(s,pos,'brake_pct')||0).toFixed(0);
    const sl=(interpAt(s,pos,'slip_rl')||0).toFixed(3);
    const g=Math.round(interpAt(s,pos,'gear'));
    lines.push(`L${ln}  ${sp}mph  G${g}  T${th}%  B${br}%  Sl${sl}`);
  });
  if(_refSamples){
    _selectedLaps.forEach(ln=>{
      if(isRefLap(ln))return;
      const s=_lapSamples[ln];if(!s)return;
      const d=interpAt(s,pos,'t')-interpAt(_refSamples,pos,'t');
      const sign=d<0?'−':'+';
      lines.push(`Δ L${ln}: ${sign}${Math.abs(d).toFixed(3)}s`);
    });
    lines.push(`@${(pos*100).toFixed(1)}%`);
  }
  if(_cursorLocked) lines.push('🔒 locked — Esc to release');
  tip.textContent=lines.join('\\n');
  updateHud(pos);
  if(mouseEvent){
    tip.style.left=Math.min(mouseEvent.clientX+14,window.innerWidth-180)+'px';
    tip.style.top=Math.max(8,mouseEvent.clientY-tip.offsetHeight-8)+'px';
    _cursorTipX=tip.style.left; _cursorTipY=tip.style.top;
  } else if(_cursorTipX!=null){
    tip.style.left=_cursorTipX; tip.style.top=_cursorTipY;
  }
  tip.style.display='block';
}

function lockCursorAt(xFrac, mouseEvent){
  _cursorLocked=true; _cursorXFrac=xFrac;
  paintCursor(xFrac, mouseEvent);
}
function unlockCursor(){
  _cursorLocked=false; _cursorXFrac=null;
  hideX();
}

function setupInteraction(){
  const area=$('charts-area');
  const tip=$('tele-tip');
  area.onmousemove=e=>{
    const wrap=e.target.closest('.panel-svg-wrap');
    if(_panning){
      const aRect=area.getBoundingClientRect();
      const dx=(e.clientX-_panX0)/aRect.width;
      const range=_panZoom0[1]-_panZoom0[0];
      let lo=_panZoom0[0]-dx*range,hi=_panZoom0[1]-dx*range;
      if(lo<0){hi-=lo;lo=0;}if(hi>1){lo-=hi-1;hi=1;}
      _zoom=[lo,hi];renderAll();
      return;
    }
    // Track whether this gesture is a drag (large movement) or click — used
    // by mouseup to decide between zoom-to-selection vs click-to-lock.
    if(_dragging && (Math.abs(e.clientX-_dragX0Abs)>4 || Math.abs(e.clientY-_dragY0)>4)){
      _dragMoved=true;
    }
    // Locked cursor — leave the line + tip at their fixed position; the mouse
    // can roam without disturbing the comparison view.
    if(_cursorLocked) return;
    if(!wrap){hideX();return;}
    const rect=wrap.getBoundingClientRect();
    const xFrac=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));
    paintCursor(xFrac, e);
    if(_dragging && _dragMoved){
      const aRect=area.getBoundingClientRect();
      const x1=e.clientX-aRect.left;
      const sel=$('drag-sel');
      sel.style.left=Math.min(_dragX0,x1)+'px';
      sel.style.width=Math.abs(x1-_dragX0)+'px';
      sel.style.display='block';
    }
  };
  area.onmouseleave=e=>{if(!_panning && !_cursorLocked) hideX();};
  area.onmousedown=e=>{
    if(!e.target.closest('.panel-svg-wrap'))return;
    e.preventDefault();
    if(_spaceDown){
      _panning=true;_panX0=e.clientX;_panZoom0=[..._zoom];
      area.querySelectorAll('.panel-svg-wrap').forEach(w=>w.classList.add('panning'));
      return;
    }
    const aRect=area.getBoundingClientRect();
    _dragging=true;
    _dragX0=e.clientX-aRect.left;
    _dragX0Abs=e.clientX; _dragY0=e.clientY;
    _dragMoved=false;
  };
  area.onmouseup=e=>{
    if(_panning){
      _panning=false;
      area.querySelectorAll('.panel-svg-wrap').forEach(w=>w.classList.remove('panning'));
      return;
    }
    if(!_dragging)return;_dragging=false;
    $('drag-sel').style.display='none';
    if(!_dragMoved){
      // Click (no meaningful drag) → toggle cursor lock at the click position.
      const wrap=e.target.closest('.panel-svg-wrap');
      if(wrap){
        if(_cursorLocked){
          unlockCursor();
        } else {
          const rect=wrap.getBoundingClientRect();
          const xFrac=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));
          lockCursorAt(xFrac, e);
        }
      }
      return;
    }
    // Drag → zoom to selection (existing behaviour).
    const aRect=area.getBoundingClientRect();
    const w=aRect.width;
    const f0=Math.max(0,Math.min(1,_dragX0/w));
    const f1=Math.max(0,Math.min(1,(e.clientX-aRect.left)/w));
    const lo=_zoom[0],hi=_zoom[1],range=hi-lo;
    const nLo=lo+Math.min(f0,f1)*range,nHi=lo+Math.max(f0,f1)*range;
    if(nHi-nLo>0.01){_zoom=[nLo,nHi];renderAll();}
  };
  // Bind document-level keydown ONCE — setupInteraction is called from
  // renderAll on every re-render, which used to add a fresh listener each
  // time. After N renders ArrowRight fired the handler N times and the
  // cursor jumped by N% per press.
  if(!window._teleKeysBound){
    window._teleKeysBound=true;
    document.addEventListener('keydown',e=>{
      if(e.target.matches('input,textarea,select'))return;
      if(e.code==='Space'){
        e.preventDefault();_spaceDown=true;
        const a=$('charts-area'); if(a) a.querySelectorAll('.panel-svg-wrap').forEach(w=>w.classList.add('panning'));
      } else if(e.code==='Escape' && _cursorLocked){
        unlockCursor();
      } else if(_cursorLocked && (e.code==='ArrowLeft' || e.code==='ArrowRight')){
        // Nudge locked cursor: ±1% of zoom window per arrow, ±10% with Shift
        e.preventDefault();
        const step=(e.shiftKey?0.10:0.01)*(e.code==='ArrowRight'?1:-1);
        _cursorXFrac=Math.max(0,Math.min(1, _cursorXFrac+step));
        paintCursor(_cursorXFrac, null);
      }
    });
  }
  // Embedded inside the Session detail iframe? Clicks on inner SVG paths
  // don't reliably give the iframe focus, so arrow keys never reach our
  // document keydown. Pull focus on any mousedown inside the chart area.
  area.addEventListener('mousedown',()=>{try{window.focus();}catch(_){} });
  if(!window._teleKeyupBound){
    window._teleKeyupBound=true;
    document.addEventListener('keyup',e=>{
      if(e.code==='Space'){
        _spaceDown=false;
        const a=$('charts-area');
        if(!_panning && a) a.querySelectorAll('.panel-svg-wrap').forEach(w=>w.classList.remove('panning'));
      }
    });
  }

  // Click on the track map → lock cursor at the corresponding lap distance.
  // Finds the sample whose px/py is closest to the click point and uses its
  // xv() position. See renderTrackMap for _tmCx / _tmCy / _tmSamples.
  const mapInner=$('track-map-inner');
  if(mapInner){
    mapInner.onclick=e=>{
      if(!_tmSamples || !_tmCx || !_tmCy) return;
      const svg=mapInner.querySelector('svg');
      if(!svg) return;
      const rect=svg.getBoundingClientRect();
      // Convert click to SVG user coords (the map uses viewBox, so scale).
      // TW/TH are now dynamic per-track; read what renderTrackMap stashed.
      const vbW=_tmTW, vbH=_tmTH;
      const sx=(e.clientX-rect.left)*(vbW/rect.width);
      const sy=(e.clientY-rect.top )*(vbH/rect.height);
      const hasPz=_tmHasPz;
      let bestI=-1, bestD=Infinity;
      for(let i=0;i<_tmSamples.length;i++){
        const ss=_tmSamples[i]; if(ss.px==null) continue;
        const z=hasPz?(ss.pz??0):(ss.py??0);
        const dx=_tmCx(ss.px)-sx, dy=_tmCy(z)-sy;
        const d=dx*dx+dy*dy;
        if(d<bestD){bestD=d;bestI=i;}
      }
      if(bestI<0) return;
      const ss=_tmSamples[bestI];
      const pos=xv(ss);
      const xFrac=(pos-_zoom[0])/(_zoom[1]-_zoom[0]);
      if(xFrac<0||xFrac>1) return;  // outside zoom window
      lockCursorAt(xFrac, e);
    };
  }
}
function hideX(){
  document.querySelectorAll('.px-line').forEach(l=>{l.style.display='none';l.classList.remove('locked');});
  $('tele-tip').style.display='none';
  resetHud();
}
// ── HUD column ────────────────────────────────────────────────────────────
// Live cockpit readouts on the right rail. Driven entirely by paintCursor:
// no separate state, no extra DB calls — just another consumer of the same
// interpolated samples that build the floating tooltip. Shows the primary
// lap vs the selected reference; hidden when no lap is selected.
function _set(id,v){const el=document.getElementById(id);if(el)el.textContent=v;}
function _setFill(id,pct){const el=document.getElementById(id);if(el)el.style.width=Math.max(0,Math.min(100,pct))+'%';}
function _setTick(id,pct){const el=document.getElementById(id);if(!el)return;
  if(pct==null||isNaN(pct)){el.style.display='none';return;}
  el.style.display='block';el.style.left=Math.max(0,Math.min(100,pct))+'%';
}
function showHud(){const c=document.getElementById('hud-col');if(c)c.style.display='';}
function hideHud(){const c=document.getElementById('hud-col');if(c)c.style.display='none';}
function resetHud(){
  // Cursor not active — clear the cards back to em-dashes so a stale read
  // doesn't look live. Lap identity stays in the header because that
  // sticks regardless of cursor (it tells you whose values you'll see
  // when you DO scrub).
  _set('hud-pos','— %');
  _setHudLapHeader();
  _set('hud-speed-val','—');_set('hud-speed-ref','');
  const sd=document.getElementById('hud-speed-delta');if(sd)sd.innerHTML='';
  _setFill('hud-thr-fill',0);_setFill('hud-brk-fill',0);
  _setTick('hud-thr-tick',null);_setTick('hud-brk-tick',null);
  _set('hud-thr-val','—');_set('hud-brk-val','—');
  _set('hud-gear-val','—');
  const dv=document.getElementById('hud-delta-val');if(dv){dv.className='hud-mid';dv.innerHTML='—<span class="hud-delta-sub">here</span>';}
}
// Header line: one chip per selected lap. Primary is filled and shows
// the HUD numbers; clicking a non-primary chip swaps focus without
// reaching back to the left ctrl-col lap list.
function _setHudLapHeader(){
  const sel=document.getElementById('hud-lapsel');
  const refRow=document.getElementById('hud-refrow');
  const refName=document.getElementById('hud-ref-name');
  if(!sel) return;
  if(!_selectedLaps.length){
    sel.innerHTML='<span style="font-size:10px;color:var(--color-text-quaternary);letter-spacing:.06em;text-transform:uppercase">No lap selected</span>';
    if(refRow) refRow.style.display='none';
    return;
  }
  sel.innerHTML=_selectedLaps.map((ln,ci)=>{
    const isPrim=ln===_primaryLap;
    return `<button type="button" class="hud-lapsel-btn${isPrim?' is-primary':''}" `+
      `style="--c:${LAP_COLORS[ci]}" data-lap="${ln}" `+
      `onclick="setPrimaryLap(${ln})" `+
      `aria-pressed="${isPrim?'true':'false'}">L${ln+1}</button>`;
  }).join('');
  if(refRow && refName){
    if(_refSamples && _primaryLap!=null && !isRefLap(_primaryLap)){
      refName.textContent=refLabel();
      refRow.style.display='';
    } else {
      refRow.style.display='none';
    }
  }
}
// Public: switch which selected lap the HUD reflects (and which trace
// renders at full opacity on the charts). No-op if the lap isn't in the
// selection set — chips are only emitted for selected laps so this
// should never be called with an invalid value.
function setPrimaryLap(lapN){
  if(_selectedLaps.indexOf(lapN) < 0) return;
  if(_primaryLap === lapN) return;
  _primaryLap = lapN;
  renderAll();
  if(_cursorLocked && _cursorXFrac != null) paintCursor(_cursorXFrac, null);
}
function updateHud(pos){
  if(!_primaryLap||!_lapSamples[_primaryLap])return;
  const s=_lapSamples[_primaryLap];
  const sp=interpAt(s,pos,'speed_mph');
  const th=interpAt(s,pos,'throttle_pct');
  const br=interpAt(s,pos,'brake_pct');
  const gr=interpAt(s,pos,'gear');
  _set('hud-pos',(pos*100).toFixed(1)+' %');
  _set('hud-speed-val',sp==null||isNaN(sp)?'—':Math.round(sp));
  _set('hud-thr-val',th==null||isNaN(th)?'—':Math.round(th)+'%');
  _set('hud-brk-val',br==null||isNaN(br)?'—':Math.round(br)+'%');
  _setFill('hud-thr-fill',th||0);
  _setFill('hud-brk-fill',br||0);
  _set('hud-gear-val',gr==null||isNaN(gr)?'—':Math.round(gr));
  // Reference comparison — only when a ref is loaded and the primary lap
  // is NOT the reference itself (showing 0 deltas vs your own lap is noise).
  if(_refSamples && !isRefLap(_primaryLap)){
    const rsp=interpAt(_refSamples,pos,'speed_mph');
    const rth=interpAt(_refSamples,pos,'throttle_pct');
    const rbr=interpAt(_refSamples,pos,'brake_pct');
    const rt=interpAt(_refSamples,pos,'t');
    const ct=interpAt(s,pos,'t');
    _set('hud-speed-ref',rsp==null||isNaN(rsp)?'':'ref '+Math.round(rsp));
    _setTick('hud-thr-tick',rth);
    _setTick('hud-brk-tick',rbr);
    const sd=document.getElementById('hud-speed-delta');
    if(sd){
      if(sp!=null&&rsp!=null&&!isNaN(sp)&&!isNaN(rsp)){
        const d=sp-rsp,sign=d>0?'+':(d<0?'−':'·'),cls=d>0?'gain':(d<0?'lost':'');
        sd.innerHTML='<span class="v '+cls+'">'+sign+Math.abs(d).toFixed(0)+' vs ref</span>';
      } else sd.innerHTML='';
    }
    const dv=document.getElementById('hud-delta-val');
    if(dv){
      if(ct!=null&&rt!=null&&!isNaN(ct)&&!isNaN(rt)){
        const dd=ct-rt,sign=dd>0?'+':(dd<0?'−':'·'),cls=dd>0?'lost':(dd<0?'gain':'');
        dv.className='hud-mid '+cls;
        dv.innerHTML=sign+Math.abs(dd).toFixed(2)+'<span class="hud-delta-sub">here</span>';
      } else { dv.className='hud-mid'; dv.innerHTML='—<span class="hud-delta-sub">here</span>'; }
    }
  } else {
    _set('hud-speed-ref','');
    _setTick('hud-thr-tick',null);_setTick('hud-brk-tick',null);
    const sd=document.getElementById('hud-speed-delta');if(sd)sd.innerHTML='';
    const dv=document.getElementById('hud-delta-val');
    if(dv){dv.className='hud-mid';dv.innerHTML='—<span class="hud-delta-sub">here</span>';}
  }
}
function resetZoom(){_zoom=[0,1];renderAll();}
function stepZoom(dir){
  const lo=_zoom[0],hi=_zoom[1],mid=(lo+hi)/2,range=hi-lo;
  const nRange=dir>0?range*0.6:range/0.6;
  const nLo=Math.max(0,mid-nRange/2),nHi=Math.min(1,mid+nRange/2);
  if(nHi-nLo>0.005){_zoom=[nLo,nHi];renderAll();}
}
function setXMode(m){
  _xMode=m;
  $('xm-dist').classList.toggle('active',m==='distance');
  $('xm-time').classList.toggle('active',m==='time');
  renderAll();
}
// ── Lap selector ──────────────────────────────────────────────────────────
function _partialThresh(){
  const validTimes=_laps.filter(l=>l.lap_time_s).map(l=>l.lap_time_s);
  if(validTimes.length<2)return 0;
  const sorted=[...validTimes].sort((a,b)=>a-b);
  const median=sorted[Math.floor(sorted.length/2)];
  return median*0.6;
}
function renderLapList(){
  const best=_sess.best_lap_time_s;
  const pThresh=_partialThresh();
  // Forza lap_number=0 IS race lap 1 — drop the lap_number > 0 carve-out.
  $('lap-list').innerHTML=_laps.filter(l=>l.lap_time_s).map(l=>{
    const ci=_selectedLaps.indexOf(l.lap_number);
    const checked=ci>=0;
    const col=checked?LAP_COLORS[ci]:'#444';
    const isBest=best&&Math.abs(l.lap_time_s-best)<0.001;
    const isPartial=pThresh>0&&l.lap_time_s<pThresh;
    const partialMark=isPartial?' <span style="font-size:.6rem;color:#555">(partial)</span>':'';
    const bestMark=isBest&&!isPartial?' <span class="lap-best-badge">★</span>':'';
    return`<label class="lap-item">
      <input type="checkbox" ${checked?'checked':''} onchange="onLapToggle(${l.lap_number},this.checked)">
      <span class="lap-swatch" style="background:${col}"></span>
      Lap ${l.lap_number + 1}${bestMark}${partialMark}
      <span class="lap-time-s">${fmtLap(l.lap_time_s)}</span>
    </label>`;
  }).join('');
  // Disable "My Best Lap" ref if that reference lap is a partial
  const refSel=$('ref-sel');
  if(refSel&&refSel.options[1]&&_refMeta&&_refMeta.best_lap){
    refSel.options[1].disabled=pThresh>0&&_refMeta.best_lap.lap_time_s<pThresh;
  }
}
async function onLapToggle(lapN,checked){
  if(checked){
    if(_selectedLaps.length>=4)_selectedLaps.shift();
    _selectedLaps.push(lapN);
    if(!_lapSamples[lapN])await fetchLap(lapN);
  }else{
    _selectedLaps=_selectedLaps.filter(n=>n!==lapN);
  }
  // Preserve user's HUD lap choice if it's still selected; otherwise
  // fall back to the first. Without this, toggling any other lap in the
  // left rail would silently snap focus back to _selectedLaps[0].
  if(_primaryLap==null || _selectedLaps.indexOf(_primaryLap)<0){
    _primaryLap = _selectedLaps[0] || null;
  }
  updateMaxT();renderLapList();renderAll();
}
async function onRefChange(){
  const newType=$('ref-sel').value;
  // Special case: "Lap from another session…" opens a picker. The actual
  // _refType isn't applied until the user picks a lap (csPickLap fires).
  // Cancel restores the previous selection — see closeCrossSessionPicker.
  if(newType==='cross_session'){
    _prevRefType=_refType;
    _refType=newType; _refSid=null; _refLapNum=null;
    openCrossSessionPicker();
    return;
  }
  _refType=newType;
  _refSamples=null;
  _refSid=null; _refLapNum=null;
  updateCrossSessionLabel();
  if(_refType)await fetchRef();
  renderAll();
}
// ── Data fetching ─────────────────────────────────────────────────────────
async function fetchLap(lapN){
  try{
    const d=await fetch('/sessions/lap-samples?session_id='+encodeURIComponent(_id)+'&lap='+lapN).then(r=>r.json());
    _lapSamples[lapN]=Array.isArray(d)&&d.length?d:[];
  }catch(e){_lapSamples[lapN]=[];}
}
function setRefStatus(msg){
  const el=$('ref-status'); if(!el)return;
  if(msg){el.textContent=msg;el.style.display='';}
  else{el.textContent='';el.style.display='none';}
}
async function fetchRef(){
  if(!_refType||!_sess){_refSamples=null;setRefStatus('');return;}
  try{
    let d;
    if(_refType==='last_lap'){
      const valid=_laps.filter(l=>l.lap_time_s);
      if(!valid.length){_refSamples=null;setRefStatus('No completed laps to reference yet.');return;}
      const lastLap=valid[valid.length-1];
      d=await fetch('/sessions/lap-samples?session_id='+encodeURIComponent(_id)+'&lap='+lastLap.lap_number).then(r=>r.json());
    } else if(_refType==='cross_session' && _refSid && _refLapNum){
      d=await fetch('/sessions/lap-samples?session_id='+encodeURIComponent(_refSid)+'&lap='+_refLapNum).then(r=>r.json());
    } else {
      d=await fetch('/sessions/reference-samples?track='+encodeURIComponent(_sess.track||'')+'&type='+_refType).then(r=>r.json());
    }
    if(Array.isArray(d)&&d.length){_refSamples=d;setRefStatus('');}
    else{_refSamples=null;setRefStatus('No lap times available to reference — go out and race.');}
  }catch(e){_refSamples=null;setRefStatus('No lap times available to reference — go out and race.');}
}

// ── Cross-session reference picker ───────────────────────────────────────
async function openCrossSessionPicker(){
  const ovl=$('cs-ovl'); const list=$('cs-list');
  list.innerHTML='<div class="cs-empty">Loading sessions…</div>';
  ovl.classList.add('open');
  const track=_sess&&_sess.track ? _sess.track : '';
  const game =_sess&&_sess.game  ? _sess.game  : '';
  let sessions=[];
  try{
    const url='/sessions/track/data?name='+encodeURIComponent(track)+(game?'&game='+encodeURIComponent(game):'');
    // /sessions/track/data returns {sessions:[...], pb:..., progress:...} —
    // a dict, not an array. The shape changed when Circuits added PB /
    // progress fields; old `.filter(...)` on the dict threw silently.
    const resp=await fetch(url).then(r=>r.json());
    sessions=Array.isArray(resp)?resp:(resp&&Array.isArray(resp.sessions)?resp.sessions:[]);
  }catch(e){sessions=[];}
  // Exclude the current session — comparing against yourself defeats the purpose
  const others=sessions.filter(s=>s.session_id!==_id);
  if(!others.length){list.innerHTML='<div class="cs-empty">No other sessions at this track yet.</div>';return;}
  list.innerHTML=others.map(s=>{
    const dt=fmtDt(s.started_at);
    const bl=s.best_lap_time_s?fmtLap(s.best_lap_time_s):'—';
    const lc=s.lap_count||0;
    return`<div class="cs-sess" data-sid="${s.session_id}" onclick="csToggleSession(this)">
      <div class="cs-sess-hd"><span>${dt}</span><span>${bl} · ${lc} lap${lc===1?'':'s'}</span></div>
      <div class="cs-sess-meta">${(s.car&&s.car!=='unknown')?s.car:''}</div>
      <div class="cs-laps"></div>
    </div>`;
  }).join('');
}
function closeCrossSessionPicker(){
  $('cs-ovl').classList.remove('open');
  // If the user opened the picker but didn't pick, restore the previous ref.
  if(_refType==='cross_session' && (!_refSid||!_refLapNum)){
    _refType=_prevRefType;
    $('ref-sel').value=_refType;
    updateCrossSessionLabel();
  }
}
async function csToggleSession(el){
  const lapsEl=el.querySelector('.cs-laps');
  if(el.classList.contains('expanded')){el.classList.remove('expanded');return;}
  // Lazy-load laps for the clicked session
  const sid=el.dataset.sid;
  lapsEl.innerHTML='<div class="cs-empty" style="padding:6px">Loading laps…</div>';
  el.classList.add('expanded');
  try{
    const d=await fetch('/sessions/session/data?id='+encodeURIComponent(sid)).then(r=>r.json());
    const laps=(d.laps||[]).filter(l=>l.lap_time_s);
    if(!laps.length){lapsEl.innerHTML='<div class="cs-empty" style="padding:6px">No valid laps in this session.</div>';return;}
    lapsEl.innerHTML=laps.map(l=>{
      const dt=d.session && d.session.started_at ? fmtDt(d.session.started_at) : '';
      const lbl=lapLabel(l.lap_number);
      return`<div class="cs-lap" data-sid="${sid}" data-lap="${l.lap_number}" data-label="${dt} · ${lbl} ${fmtLap(l.lap_time_s)}" onclick="csPickLap(this)">${lbl} — ${fmtLap(l.lap_time_s)}</div>`;
    }).join('');
  }catch(e){lapsEl.innerHTML='<div class="cs-empty" style="padding:6px">Error loading laps.</div>';}
}
async function csPickLap(el){
  _refSid=el.dataset.sid;
  _refLapNum=parseInt(el.dataset.lap, 10);
  _refType='cross_session';
  $('cs-ovl').classList.remove('open');
  // Surface the picked lap's identity in the sidebar so the user remembers
  // what they're comparing against.
  const labelEl=$('cs-ref-label');
  labelEl.textContent='ref: '+el.dataset.label;
  labelEl.style.display='';
  await fetchRef();
  renderAll();
}
function updateCrossSessionLabel(){
  const labelEl=$('cs-ref-label');
  if(!labelEl)return;
  if(_refType==='cross_session' && _refSid && _refLapNum){
    labelEl.style.display='';
  } else {
    labelEl.style.display='none';
    labelEl.textContent='';
  }
}
function updateMaxT(){
  _maxT=0;
  for(const s of Object.values(_lapSamples)){if(s&&s.length){const t=s[s.length-1].t||0;if(t>_maxT)_maxT=t;}}
  if(_refSamples&&_refSamples.length){const t=_refSamples[_refSamples.length-1].t||0;if(t>_maxT)_maxT=t;}
  if(!_maxT)_maxT=1;
}
// ── Init ──────────────────────────────────────────────────────────────────
const _isEmbed=new URLSearchParams(location.search).get('embed')==='1';
async function init(){
  if(!_id){location.href='/sessions';return;}
  if(_isEmbed){const bc=$('tele-breadcrumb');if(bc)bc.style.display='none';const sn=$('tele-subnav');if(sn)sn.style.display='none';}
  if(window.Perf)Perf.mark('init:start');
  let d;
  try{d=await fetch('/sessions/session/data?id='+encodeURIComponent(_id)).then(r=>r.json());}
  catch(e){$('tele-loading').textContent='Session not found';return;}
  if(window.Perf)Perf.measure('fetch:session', 'init:start');
  _sess=d.session;_laps=d.laps||[];
  // Breadcrumb
  const track=(_sess.track&&_sess.track!=='unknown')?_sess.track:(_strack||'Unknown');
  const game=_sgame||_sess.game||'';
  const GL={'forza_motorsport':'Forza','acc':'ACC','f1':'F1'};
  document.title='Pacefinder · '+track+' Telemetry';
  if(game){const b=$('bc-game');b.textContent=GL[game]||game;b.href='/sessions/game?name='+encodeURIComponent(game);b.style.display='';$('bc-gsep').style.display='';}
  $('bc-track').textContent=track;
  $('bc-track').href='/sessions/track?name='+encodeURIComponent(track)+(game?'&game='+encodeURIComponent(game):'');
  $('bc-sess').textContent=fmtDt(_sess.started_at);
  let sessHref='/sessions/session?id='+encodeURIComponent(_id);
  if(game)sessHref+='&game='+encodeURIComponent(game);
  if(track)sessHref+='&track='+encodeURIComponent(track);
  $('bc-sess').href=sessHref;
  $('link-overview').href=sessHref;
  // Best lap default — skip partial laps. Overridden when the URL carries
  // ?lap=N (e.g. a Spotter coaching card deep-linked into this specific
  // lap so the user lands on the trace the finding is about).
  const best=_sess.best_lap_time_s;
  const validLaps=_laps.filter(l=>l.lap_time_s);
  const pThreshInit=_partialThresh();
  const nonPartialLaps=pThreshInit>0?validLaps.filter(l=>l.lap_time_s>=pThreshInit):validLaps;
  const bestLap=nonPartialLaps.find(l=>best&&Math.abs(l.lap_time_s-best)<0.001)||nonPartialLaps[0]||validLaps[0];
  const qLapRaw=new URLSearchParams(location.search).get('lap');
  const qLap=qLapRaw!=null && qLapRaw!=='' ? parseInt(qLapRaw,10) : NaN;
  let chosen=null;
  if(!isNaN(qLap)){
    chosen=_laps.find(l=>l.lap_number===qLap && l.lap_time_s) || null;
  }
  if(!chosen) chosen=bestLap;
  if(chosen){
    _selectedLaps=[chosen.lap_number];
    _primaryLap=chosen.lap_number;
    await fetchLap(chosen.lap_number);
  }
  // Reference metadata
  try{
    _refMeta=await fetch('/sessions/references?track='+encodeURIComponent(_sess.track||'')+'&game='+encodeURIComponent(_sess.game||'')).then(r=>r.json());
    if(_refMeta.best_lap&&$('ref-sel').options[1])$('ref-sel').options[1].text='My Best — '+fmtLap(_refMeta.best_lap.lap_time_s);
    if(_refMeta.theoretical&&$('ref-sel').options[2])$('ref-sel').options[2].text='Theoretical — '+fmtLap(_refMeta.theoretical.theoretical_best_s);
    // Last Lap option label — most recent completed lap of THIS session
    const validLaps=_laps.filter(l=>l.lap_time_s);
    if(validLaps.length && $('ref-sel').options[3]){
      const lastLap=validLaps[validLaps.length-1];
      $('ref-sel').options[3].text='Last Lap — '+lapLabel(lastLap.lap_number)+' '+fmtLap(lastLap.lap_time_s);
    }
    // Auto-skip partial reference
    if(_refMeta.best_lap&&pThreshInit>0&&_refMeta.best_lap.lap_time_s<pThreshInit){
      $('ref-sel').value=_refMeta.theoretical?'theoretical':'';
      _refType=$('ref-sel').value;
    }
  }catch(e){}
  if(window.Perf)Perf.mark('ref:start');
  await fetchRef();
  if(window.Perf)Perf.measure('fetch:ref', 'ref:start');
  updateMaxT();
  $('tele-loading').style.display='none';
  $('ctrl-loading').style.display='none';
  $('panels-inner').style.display='';
  $('ctrl-inner').style.display='';
  renderLapList();
  if(window.Perf)Perf.mark('render:start');
  renderAll();
  if(window.Perf){Perf.measure('render:initial', 'render:start');Perf.measure('init:total','init:start');}
}
init();

// Mistakes & opportunities — modal-only (docs/specs/mistakes-modal.md).
// Embeds the events view; the standalone page 301s here when hit
// directly. Opened from the subnav or via ?events=1 (Overview teaser).
(function(){
  if(_isEmbed) return; // telemetry itself is embedded — no nested modal
  var ovl=$('mo-ovl'), f=$('mo-if'), btn=$('link-mistakes'), x=$('mo-x');
  if(!ovl) return;
  function open(){
    if(f.dataset.l!=='1'){ f.src='/sessions/session/events?id='+encodeURIComponent(_id)+'&embed=1'; f.dataset.l='1'; }
    ovl.classList.add('open');
  }
  function close(){ ovl.classList.remove('open'); }
  if(btn) btn.addEventListener('click', open);
  if(x) x.addEventListener('click', close);
  ovl.addEventListener('click', function(e){ if(e.target===ovl) close(); });
  if(new URLSearchParams(location.search).get('events')==='1') open();
})();
