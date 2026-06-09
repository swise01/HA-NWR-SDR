// Deep Dive tab — fetches /sessions/session/deepdive and renders track map,
// G-G diagram, speed-trace overlay, lap-comparison summary, and events list.
// Vanilla SVG/Canvas only, namespaced under window.DeepDive so the entry point
// is callable from sessions_session.js's switchTab().
//
// Spec: docs/specs/deep-dive-tab.md.
(function(){
  const SVG_NS='http://www.w3.org/2000/svg';
  let _id=null,_data=null,_selectedLap=null,_channel='speed';

  // ── Color palettes ──────────────────────────────────────────────
  // Speed: viridis-ish 5-stop ramp 0→max.
  const SPEED_STOPS=['#440154','#3b528b','#21918c','#5ec962','#fde725'];
  const GEAR_COLORS=['#666','#3b82f6','#22c55e','#84cc16','#eab308','#f97316','#ef4444','#ec4899','#a855f7'];

  function lerp(a,b,t){return a+(b-a)*t;}
  function hex2rgb(hex){const n=parseInt(hex.slice(1),16);return [(n>>16)&255,(n>>8)&255,n&255];}
  function rgb2hex(r,g,b){return '#'+[r,g,b].map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');}
  function rampColor(stops,frac){
    if(frac<=0)return stops[0];
    if(frac>=1)return stops[stops.length-1];
    const i=frac*(stops.length-1);
    const lo=Math.floor(i), hi=Math.min(lo+1,stops.length-1);
    const t=i-lo;
    const a=hex2rgb(stops[lo]), b=hex2rgb(stops[hi]);
    return rgb2hex(lerp(a[0],b[0],t),lerp(a[1],b[1],t),lerp(a[2],b[2],t));
  }
  function channelColor(ch,sample,scale){
    // sample = [px, pz, dist, speed, thr, brk, gear, slip]
    if(ch==='speed') return rampColor(SPEED_STOPS, scale.speed?(sample[3]/scale.speed):0);
    if(ch==='throttle'){
      const f=sample[4]/100;
      // gray → green
      const g=Math.round(lerp(80,34,f)),r=Math.round(lerp(80,197,f<0.5?0:(f-0.5)*2)),b=Math.round(lerp(80,94,f));
      return `rgb(${r},${g},${b})`;
    }
    if(ch==='brake'){
      const f=sample[5]/100;
      return `rgba(${Math.round(lerp(80,239,f))},${Math.round(lerp(80,68,f))},${Math.round(lerp(80,68,f))},1)`;
    }
    if(ch==='slip'){
      const f=Math.min(1, sample[7]/0.5);
      // gray → amber → red
      if(f<0.5) return rgb2hex(lerp(80,245,f*2),lerp(80,158,f*2),lerp(80,11,f*2));
      const t=(f-0.5)*2;
      return rgb2hex(lerp(245,239,t),lerp(158,68,t),lerp(11,68,t));
    }
    if(ch==='gear') return GEAR_COLORS[Math.max(0,Math.min(8,sample[6]))]||'#888';
    return '#888';
  }

  // ── Render: track map ───────────────────────────────────────────
  function renderTrackMap(){
    const svg=document.getElementById('dd-map');
    svg.innerHTML='';
    const tm=_data.track_map;
    if(!_data.track_map_available || !tm.laps.length){
      svg.innerHTML='<text x="50%" y="50%" fill="#888" text-anchor="middle" dominant-baseline="middle" font-size="14">Older session — track map unavailable</text>';
      return;
    }
    // Compute bounding box across all laps + scale.
    let xmin=Infinity,xmax=-Infinity,zmin=Infinity,zmax=-Infinity,smax=0;
    for(const lap of tm.laps){
      for(const p of lap.points){
        if(p[0]<xmin)xmin=p[0]; if(p[0]>xmax)xmax=p[0];
        if(p[1]<zmin)zmin=p[1]; if(p[1]>zmax)zmax=p[1];
        if(p[3]>smax)smax=p[3];
      }
    }
    const W=svg.clientWidth||800,H=svg.clientHeight||500;
    const pad=20;
    const xspan=xmax-xmin||1, zspan=zmax-zmin||1;
    const sx=(W-2*pad)/xspan, sz=(H-2*pad)/zspan, s=Math.min(sx,sz);
    const ox=pad+(W-2*pad-xspan*s)/2, oz=pad+(H-2*pad-zspan*s)/2;
    const proj=(px,pz)=>[ox+(px-xmin)*s, oz+(pz-zmin)*s];
    svg.setAttribute('viewBox',`0 0 ${W} ${H}`);

    // Ghost lines for non-selected laps.
    for(const lap of tm.laps){
      if(lap.lap_number===_selectedLap)continue;
      const path=document.createElementNS(SVG_NS,'path');
      let d='';
      for(let i=0;i<lap.points.length;i++){
        const [x,y]=proj(lap.points[i][0],lap.points[i][1]);
        d+=(i?' L':'M')+x.toFixed(1)+' '+y.toFixed(1);
      }
      path.setAttribute('d',d);
      path.setAttribute('fill','none');
      path.setAttribute('stroke','#666');
      path.setAttribute('stroke-width','1');
      path.setAttribute('opacity','0.18');
      svg.appendChild(path);
    }

    // Selected lap — segmented colored polyline (each segment colored by channel value at start).
    const sel=tm.laps.find(l=>l.lap_number===_selectedLap)||tm.laps[0];
    const scale={speed:smax};
    for(let i=1;i<sel.points.length;i++){
      const [x0,y0]=proj(sel.points[i-1][0],sel.points[i-1][1]);
      const [x1,y1]=proj(sel.points[i][0],sel.points[i][1]);
      const seg=document.createElementNS(SVG_NS,'line');
      seg.setAttribute('x1',x0.toFixed(1));
      seg.setAttribute('y1',y0.toFixed(1));
      seg.setAttribute('x2',x1.toFixed(1));
      seg.setAttribute('y2',y1.toFixed(1));
      seg.setAttribute('stroke',channelColor(_channel,sel.points[i-1],scale));
      seg.setAttribute('stroke-width','3');
      seg.setAttribute('stroke-linecap','round');
      svg.appendChild(seg);
    }

    // Event markers on the selected lap.
    const tip=document.getElementById('dd-map-tip');
    for(const ev of _data.events){
      if(ev.lap_number!==_selectedLap)continue;
      // Find the point closest to ev.distance_m.
      let closest=sel.points[0],best=Math.abs(closest[2]-ev.distance_m);
      for(const p of sel.points){
        const d=Math.abs(p[2]-ev.distance_m);
        if(d<best){best=d;closest=p;}
      }
      const [x,y]=proj(closest[0],closest[1]);
      const c=document.createElementNS(SVG_NS,'circle');
      c.setAttribute('cx',x.toFixed(1));
      c.setAttribute('cy',y.toFixed(1));
      c.setAttribute('r','5');
      c.setAttribute('fill','#ef4444');
      c.setAttribute('stroke','#fff');
      c.setAttribute('stroke-width','1.5');
      c.style.cursor='pointer';
      c.addEventListener('mouseenter',e=>{
        tip.textContent=`${ev.label} · ${ev.detail}`;
        tip.style.display='block';
        tip.style.left=(e.offsetX+10)+'px';
        tip.style.top=(e.offsetY+10)+'px';
      });
      c.addEventListener('mouseleave',()=>{tip.style.display='none';});
      svg.appendChild(c);
    }
  }

  // ── Render: G-G diagram ─────────────────────────────────────────
  function renderGG(){
    const cv=document.getElementById('dd-gg');
    const w=cv.width,h=cv.height;
    const ctx=cv.getContext('2d');
    ctx.fillStyle='#0a0a0a';
    ctx.fillRect(0,0,w,h);
    // Reference circle at ±2g — could adapt later.
    const cx=w/2,cy=h/2,scale=Math.min(w,h)/2-12;
    const limit=2.0;
    ctx.strokeStyle='#333';
    ctx.lineWidth=1;
    ctx.beginPath();ctx.arc(cx,cy,scale,0,Math.PI*2);ctx.stroke();
    // Crosshair
    ctx.beginPath();ctx.moveTo(cx-scale,cy);ctx.lineTo(cx+scale,cy);ctx.moveTo(cx,cy-scale);ctx.lineTo(cx,cy+scale);ctx.stroke();
    // Labels
    ctx.fillStyle='#666';ctx.font='10px ui-monospace,monospace';
    ctx.fillText('+2g lat',cx+scale-30,cy-4);
    ctx.fillText('+2g lon',cx+4,cy-scale+10);
    // Selected lap dots, others faint.
    for(const lap of _data.gg.laps){
      const isSel=lap.lap_number===_selectedLap;
      ctx.fillStyle=isSel?'#22c55e':'#444';
      const r=isSel?1.5:1;
      for(const p of lap.points){
        const x=cx+(p[1]/limit)*scale;   // g_lat → x
        const y=cy-(p[0]/limit)*scale;   // g_lon → y (positive up = braking)
        if(x<0||x>w||y<0||y>h)continue;
        ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
      }
    }
  }

  // ── Render: speed trace ─────────────────────────────────────────
  function renderSpeedTrace(){
    const svg=document.getElementById('dd-speed');
    svg.innerHTML='';
    const st=_data.speed_trace;
    if(!st.laps.length){return;}
    let dmax=0,smax=0;
    for(const lap of st.laps)for(const p of lap.points){if(p[0]>dmax)dmax=p[0];if(p[1]>smax)smax=p[1];}
    if(dmax<=0)return;
    const W=svg.clientWidth||800,H=svg.clientHeight||220;
    const pad=24;
    svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
    const proj=(d,sp)=>[pad+(d/dmax)*(W-2*pad), H-pad-(sp/smax)*(H-2*pad)];
    // Y-axis ticks every 50 mph
    for(let v=0;v<=smax;v+=50){
      const y=H-pad-(v/smax)*(H-2*pad);
      const ln=document.createElementNS(SVG_NS,'line');
      ln.setAttribute('x1',pad);ln.setAttribute('x2',W-pad);
      ln.setAttribute('y1',y);ln.setAttribute('y2',y);
      ln.setAttribute('stroke','#222');ln.setAttribute('stroke-width','1');
      svg.appendChild(ln);
      const t=document.createElementNS(SVG_NS,'text');
      t.setAttribute('x',4);t.setAttribute('y',y+3);
      t.setAttribute('fill','#666');t.setAttribute('font-size','9');
      t.textContent=v;
      svg.appendChild(t);
    }
    for(const lap of st.laps){
      const isSel=lap.lap_number===_selectedLap;
      const path=document.createElementNS(SVG_NS,'path');
      let d='';
      for(let i=0;i<lap.points.length;i++){
        const [x,y]=proj(lap.points[i][0],lap.points[i][1]);
        d+=(i?' L':'M')+x.toFixed(1)+' '+y.toFixed(1);
      }
      path.setAttribute('d',d);
      path.setAttribute('fill','none');
      path.setAttribute('stroke',isSel?'#22c55e':'#555');
      path.setAttribute('stroke-width',isSel?'1.8':'0.8');
      path.setAttribute('opacity',isSel?'1':'0.35');
      svg.appendChild(path);
    }
  }

  // ── Render: events list ─────────────────────────────────────────
  function renderEvents(){
    const el=document.getElementById('dd-events');
    if(!_data.events.length){
      el.innerHTML='<div class="dd-empty-msg">Clean session — no incidents flagged.</div>';
      return;
    }
    const visible=_data.events.slice(0,10);
    el.innerHTML=visible.map(ev=>`
      <div class="dd-event" data-lap="${ev.lap_number}" data-dist="${ev.distance_m}">
        <span class="dd-ev-kind dd-ev-${ev.kind}">${ev.label}</span>
        <span class="dd-ev-loc">L${ev.lap_number+1} @ ${Math.round(ev.distance_m)} m</span>
        <span class="dd-ev-detail">${ev.detail}</span>
      </div>`).join('');
    if(_data.events.length>10){
      el.innerHTML+=`<div class="dd-empty-msg">+${_data.events.length-10} more (collapsed)</div>`;
    }
    el.querySelectorAll('.dd-event').forEach(node=>{
      node.addEventListener('click',()=>{
        const lap=parseInt(node.dataset.lap,10);
        if(_selectedLap!==lap){_selectedLap=lap;rerender();}
      });
    });
  }

  // ── Render: lap comparison summary ──────────────────────────────
  function renderLapComparison(){
    const sum=document.getElementById('dd-cmp-summary');
    const lc=_data.lap_comparison;
    if(!lc){sum.innerHTML='<div class="dd-empty-msg">Need at least two laps with samples.</div>';return;}
    const sign=lc.total_delta_s>=0?'+':'';
    sum.innerHTML=`
      <div class="dd-cmp-total">L${lc.compare_lap+1} vs L${lc.reference_lap+1}: <span class="${lc.total_delta_s>0?'lost':'gained'}">${sign}${lc.total_delta_s.toFixed(3)}s</span></div>
      <div class="dd-cmp-cols">
        <div>
          <div class="dd-cmp-h">Top lost</div>
          ${lc.top_lost.length?lc.top_lost.map(s=>`<div class="dd-cmp-seg lost">+${s.delta_s.toFixed(2)}s @ ${Math.round(s.start_m)}–${Math.round(s.end_m)} m</div>`).join(''):'<div class="dd-empty-msg">—</div>'}
        </div>
        <div>
          <div class="dd-cmp-h">Top gained</div>
          ${lc.top_gained.length?lc.top_gained.map(s=>`<div class="dd-cmp-seg gained">${s.delta_s.toFixed(2)}s @ ${Math.round(s.start_m)}–${Math.round(s.end_m)} m</div>`).join(''):'<div class="dd-empty-msg">—</div>'}
        </div>
      </div>`;
  }

  // ── Render: headline ────────────────────────────────────────────
  function renderHeadline(){
    const el=document.getElementById('dd-headline');
    el.innerHTML=_data.headline.map(h=>`<div class="dd-hl"><span class="l">${h.label}</span><span class="v">${h.value}</span></div>`).join('');
  }

  // ── Render: lap selector + cmp dropdowns ────────────────────────
  function renderLapPickers(){
    const row=document.getElementById('dd-lap-row');
    row.innerHTML=_data.lap_numbers.map(n=>
      `<button class="dd-chip${n===_selectedLap?' active':''}" data-lap="${n}">L${n+1}</button>`
    ).join('');
    row.querySelectorAll('.dd-chip').forEach(b=>b.addEventListener('click',()=>{
      _selectedLap=parseInt(b.dataset.lap,10);
      rerender();
    }));
    // Comparison dropdowns.
    for(const which of ['ref','cmp']){
      const sel=document.getElementById(`dd-cmp-${which}`);
      sel.innerHTML=_data.lap_numbers.map(n=>`<option value="${n}">L${n+1}</option>`).join('');
      const cur=_data.lap_comparison?(which==='ref'?_data.lap_comparison.reference_lap:_data.lap_comparison.compare_lap):null;
      if(cur!=null) sel.value=cur;
      sel.onchange=async()=>{await refetchComparison();};
    }
  }

  async function refetchComparison(){
    const ref=document.getElementById('dd-cmp-ref').value;
    const cmp=document.getElementById('dd-cmp-cmp').value;
    try{
      const d=await fetch(`/sessions/session/deepdive?id=${encodeURIComponent(_id)}&ref=${ref}&cmp=${cmp}`).then(r=>r.json());
      _data.lap_comparison=d.lap_comparison;
      renderLapComparison();
    }catch(e){/* ignore */}
  }

  // ── Channel chip wiring ─────────────────────────────────────────
  function wireChannelChips(){
    document.querySelectorAll('#dd-channels .dd-chip').forEach(b=>{
      b.addEventListener('click',()=>{
        document.querySelectorAll('#dd-channels .dd-chip').forEach(x=>x.classList.remove('active'));
        b.classList.add('active');
        _channel=b.dataset.ch;
        renderTrackMap();
      });
    });
  }

  function rerender(){
    renderHeadline();
    renderLapPickers();
    renderTrackMap();
    renderGG();
    renderSpeedTrace();
    renderEvents();
    renderLapComparison();
  }

  // ── Public entry ────────────────────────────────────────────────
  async function init(sessionId){
    _id=sessionId;
    const empty=document.getElementById('dd-empty');
    try{
      _data=await fetch(`/sessions/session/deepdive?id=${encodeURIComponent(_id)}`).then(r=>r.json());
    }catch(e){
      empty.style.display='block';
      empty.textContent='Could not load Deep Dive.';
      return;
    }
    if(!_data.lap_numbers||!_data.lap_numbers.length){
      empty.style.display='block';
      empty.textContent='Need at least one valid lap with stored samples for Deep Dive.';
      return;
    }
    _selectedLap=_data.lap_numbers[0];
    // Prefer the best lap as the selected lap, if we know which it is.
    if(_data.lap_comparison && _data.lap_comparison.reference_lap!=null){
      _selectedLap=_data.lap_comparison.reference_lap;
    }
    wireChannelChips();
    rerender();
  }

  window.DeepDive={init};
})();
