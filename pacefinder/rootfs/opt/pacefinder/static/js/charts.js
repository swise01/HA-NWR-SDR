// ── Formatting ───────────────────────────────────────────────────────────────
function fmtLap(s){if(!s)return'—';const m=Math.floor(s/60);return m+':'+(s%60).toFixed(3).padStart(6,'0');}
function fmtDt(iso){if(!iso)return'—';return new Date(iso).toLocaleString([],{month:'short',day:'numeric',year:'2-digit',hour:'2-digit',minute:'2-digit'});}
// ── Auto range helper ─────────────────────────────────────────────────────────
function autoRange(listOfSamples,field,pad=0.06){
  let mn=Infinity,mx=-Infinity;
  for(const ss of listOfSamples){for(const s of(ss||[])){const v=s[field];if(v!=null){if(v<mn)mn=v;if(v>mx)mx=v;}}}
  if(!isFinite(mn)){mn=0;mx=1;}
  if(mn===mx){mn-=1;mx+=1;}
  const p=(mx-mn)*pad;return[mn-p,mx+p];
}
// ── SVG path builders (call zs/sX/W globals from telemetry.js) ───────────────
function linePts(samples,field,H,mn,mx){
  const sl=zs(samples);if(!sl.length)return'';
  const yr=mx-mn||1;
  return'M'+sl.map(s=>`${sX(s).toFixed(1)},${(H-((s[field]??mn)-mn)/yr*H).toFixed(1)}`).join('L');
}
function fillPts(samples,field,H,mn,mx){
  const sl=zs(samples);if(!sl.length)return'';
  const yr=mx-mn||1;
  const pts=sl.map(s=>`${sX(s).toFixed(1)},${(H-((s[field]??mn)-mn)/yr*H).toFixed(1)}`);
  const x0=sX(sl[0]).toFixed(1),xN=sX(sl[sl.length-1]).toFixed(1);
  return'M'+pts.join('L')+`L${xN},${H}L${x0},${H}Z`;
}
function stepPts(samples,field,H,mn,mx){
  const sl=zs(samples);if(!sl.length)return'';
  const yr=mx-mn||1;
  let d='';
  for(let i=0;i<sl.length;i++){
    const x=sX(sl[i]).toFixed(1);
    const y=(H-((Math.max(mn,sl[i][field]??mn)-mn)/yr*H)).toFixed(1);
    d+=i===0?`M${x},${y}`:`H${x}V${y}`;
  }
  return d;
}
// ── Sector line/label helpers (call normToSX/W globals from telemetry.js) ─────
function secLine(frac,H){
  const x=normToSX(frac).toFixed(1);
  if(x<-10||x>W+10)return'';
  return`<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="#444" stroke-width="1" stroke-dasharray="4,3" opacity=".6"/>`;
}
function secLabel(frac,lbl,H){
  const x=normToSX(frac).toFixed(1);
  if(x<0||x>W-30)return'';
  return`<text x="${parseFloat(x)+5}" y="14" fill="#444" font-size="20" font-family="monospace">${lbl}</text>`;
}
// ── Speed to RGB (track map) ──────────────────────────────────────────────────
function spdRgb(v,mn,mx){
  const t=Math.max(0,Math.min(1,(v-mn)/(mx-mn||1)));
  return`rgb(${Math.round(t<.5?0:(t-.5)*510)},${Math.round(t<.5?t*360:(1-(t-.5)*2)*360)},${Math.round(t<.5?255-t*510:0)})`;
}
