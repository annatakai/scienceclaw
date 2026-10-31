/* Dig Once map replay. ALL ASSET DATA SIMULATED. Presentation only: every value comes from data/*.json|bin written by
   demo/build_demo.py from the simulation record. MapLibre GL JS is vendored in vendor/ (no CDN needed). */
(function () {
'use strict';
const $ = (s, r) => (r || document).querySelector(s);
const el = (tag, attrs, html) => { const e = document.createElement(tag); Object.assign(e, attrs || {}); if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const store = { get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };
const fmtM = v => '$' + (v / 1e6).toFixed(1) + 'M';
const fmtD = v => '$' + Math.round(v).toLocaleString('en-US');

const RISK = [['Low', '#fee391'], ['Moderate', '#fe9929'], ['High', '#cc4c02'], ['Critical', '#662506']];   // YlOrBr, colourblind safe
const COND = [['Good', '#c6dbef'], ['Fair', '#6baed6'], ['Poor', '#2171b5'], ['Failed', '#08306b']];       // Blues
const MAT = ['Cast iron', 'Ductile iron', 'PVC', 'Steel', 'Protected ductile iron'];
const WORK = { replace_pipe: 'replace pipe', reline_pipe: 'reline pipe', repave: 'repave' };
const AGENT = { p: 'pipe', r: 'road', b: 'budget' };
const PHASES = ['Rate', 'Plan', 'Negotiate', 'Fund', 'Apply'];
const STRAT = {
  isolated: ['Isolated departments', '#7b8494'], pooled: ['Pooled budget', '#d97706'], coordinated: ['Agents + board', '#2563eb'],
  coordinated_llm: ['Agents + board (Claude)', '#7c3aed'], central: ['Central planner (heuristic)', '#0f766e']
};
// stops: zoom -> line width by road class (arterial, collector, local). Locals are hidden when zoomed far out.
const WSTOPS = [[9, 0.8, 0.5, 0], [11.5, 1.4, 1, 0], [12, 1.8, 1.3, 0.8], [14, 4, 3, 2], [16, 9, 7, 5], [18, 16, 13, 10]];
const Z = { a: 14, b: 14 };

let meta, geo, N = 0, bbox = [], names = [], nbIdx;
const bins = {}, jsons = {}, yidx = {};
const S = { strategy: 'coordinated', frame: 0, phase: 4, playing: false, speed: 1, sel: -1, hover: -1, nb: '', basemap: 'light', theme: 'light',
  layers: { risk: true, cond: false, plan: false, shared: true, funded: true, breaks: true }, op: { risk: 100, cond: 70, plan: 100, shared: 70, funded: 70, breaks: 100, basemap: 100 },
  chips: { pipe: true, road: true, budget: true, board: true, fail: true }, sort: { col: 'risk', dir: -1 }, tq: '' };
let map = null, timer = null, styleReady = false, toastT = null;
const applied = {};
const target = {};

/* ---------- boot ---------- */
async function boot() {
  const th = store.get('dg-theme', 'light'); setTheme(th, true);
  if (typeof maplibregl === 'undefined') return noMap('The map library failed to load (vendor/maplibre-gl.js). The side panels still work.');
  if (!maplibregl.supported || !maplibregl.supported()) { /* newer builds drop supported(); creation below reports WebGL failure */ }
  try {
    [meta, geo] = await Promise.all([fetch('data/meta.json').then(r => r.json()), fetch('data/segments.geojson').then(r => r.json())]);
  } catch (e) { return noMap('Could not load the simulation data (data/). Run: python3 -m demo.build_demo'); }
  N = meta.n; S.frame = 0; S.strategy = meta.order.includes('coordinated') ? 'coordinated' : meta.order[0];
  prepGeo(); buildStaticUI();
  await loadStrategy(S.strategy);
  initMap();
  loadRest();
}

function noMap(msg) { const n = $('#nomap'); n.hidden = false; n.textContent = msg; }

function prepGeo() {
  nbIdx = new Uint8Array(N);
  geo.features.forEach((f, i) => {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const [x, y] of f.geometry.coordinates) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    bbox[i] = [x0, y0, x1, y1];
    nbIdx[i] = Math.max(0, meta.nbs.indexOf(f.properties.nb) + 1);
  });
  const by = {};
  geo.features.forEach((f, i) => { (by[f.properties.street] = by[f.properties.street] || []).push(i); });
  names = Object.keys(by).sort().map(n => ({ n, ids: by[n], l: n.toLowerCase() }));
}

async function loadStrategy(s) {
  if (bins[s]) return;
  const [b, j] = await Promise.all([fetch(`data/${s}.bin`).then(r => r.arrayBuffer()), fetch(`data/${s}.json`).then(r => r.json())]);
  bins[s] = new Uint8Array(b); jsons[s] = j; yidx[s] = {};
}
async function loadRest() { for (const s of meta.order.filter(s => !bins[s])) { try { await loadStrategy(s); if (curTab() === 'compare') renderCompare(); } catch (e) { /* retried when the strategy is chosen */ } } }

/* ---------- state access ---------- */
const F = i => meta.fields.indexOf(i);
function plane(strategy, frame, field) {
  const o = (frame * meta.fields.length + F(field)) * N;
  return bins[strategy].subarray(o, o + N);
}
const val = (field, i, frame) => { const v = plane(S.strategy, frame == null ? shownFrame() : frame, field)[i]; return meta.offset[field] ? v + meta.offset[field] : v; };
const yearOf = f => jsons[S.strategy].years[f - 1];
function shownFrame() { return (S.playing && S.phase < 4 && S.frame > 0) ? S.frame - 1 : S.frame; }
function lookups(f) {
  const c = yidx[S.strategy];
  if (c[f]) return c[f];
  const y = yearOf(f), plan = new Map(y.plans), funded = new Map(), rej = new Map();
  for (const d of y.funded) (funded.get(d[0]) || funded.set(d[0], []).get(d[0])).push(d);
  for (const d of y.rejected) (rej.get(d[0]) || rej.set(d[0], []).get(d[0])).push(d);
  return (c[f] = { plan, funded, rej });
}

/* ---------- map ---------- */
const W = f => ['interpolate', ['linear'], ['zoom'], ...WSTOPS.flatMap(s => [s[0], ['match', ['get', 'cls'], 'arterial', f(s[1]), 'collector', f(s[2]), f(s[3])]])];
const st = (k, d) => ['coalesce', ['feature-state', k], d];
const riskColor = ['match', st('rc', -1), ...RISK.flatMap((r, i) => [i, r[1]]), '#c5cad3'];
const condColor = ['match', st('cc', -1), ...COND.flatMap((r, i) => [i, r[1]]), '#c5cad3'];
const BLANK = bg => ({ version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': bg } }] });
const OSM = { version: 8, sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' } }, layers: [{ id: 'osm', type: 'raster', source: 'osm' }] };
const OSM_MUTED = JSON.parse(JSON.stringify(OSM)); OSM_MUTED.layers[0].paint = { 'raster-saturation': -1, 'raster-contrast': -0.35, 'raster-brightness-min': 0.45, 'raster-brightness-max': 1 };
const BASE = { light: { label: 'Light', style: OSM_MUTED }, dark: { label: 'Dark', url: 'https://tiles.openfreemap.org/styles/dark' }, osm: { label: 'OSM standard' }, none: { label: 'None' } };
const bgColor = () => S.theme === 'dark' ? '#0f141b' : '#eef0f3';

function initMap() {
  try {
    map = new maplibregl.Map({ container: 'map', style: BLANK(bgColor()), bounds: dataBounds(), fitBoundsOptions: { padding: 32 }, attributionControl: false,
      maxPitch: 0, pitchWithRotate: false, dragRotate: true, doubleClickZoom: true, hash: false, minZoom: 8, maxZoom: 19, fadeDuration: 0 });
  } catch (e) { return noMap('This browser could not start WebGL, so the map cannot be drawn. The panels still work.'); }
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
  const home = el('div', { className: 'maplibregl-ctrl maplibregl-ctrl-group' });
  const hb = el('button', { type: 'button', title: 'Fit the whole network (F)', ariaLabel: 'Fit to data' }, '<svg viewBox="0 0 16 16" width="16" height="16" style="margin:8px"><path d="M2 8l6-5 6 5M4 7v6h3V9h2v4h3V7" fill="none" stroke="#333" stroke-width="1.4" stroke-linejoin="round"/></svg>');
  hb.onclick = fitAll; home.appendChild(hb);
  map.addControl({ onAdd() { return home; }, onRemove() { home.remove(); } }, 'top-left');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'imperial' }), 'bottom-left');
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'Streets: Analyze Boston, MassDOT. Asset data simulated.' }), 'bottom-right');
  let tileErrs = 0;
  map.on('error', e => {   // tile and style fetch failures are expected offline: stay silent, and give up on a dead basemap
    if (e && e.sourceId === 'osm' && ++tileErrs === 6 && S.basemap !== 'none') { toast('Basemap tiles unreachable, showing None'); setBasemap('none', true); tileErrs = 0; }
  });
  map.on('style.load', onStyle);
  map.on('styleimagemissing', e => { if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
  map.on('mousemove', e => { $('#ll').textContent = `lat ${e.lngLat.lat.toFixed(5)}, lon ${e.lngLat.lng.toFixed(5)}`; });
  map.on('mouseout', () => { $('#ll').textContent = 'lat --, lon --'; });
  const z = () => { $('#zl').textContent = 'zoom ' + map.getZoom().toFixed(1); };
  map.on('zoom', z); map.on('load', z);
  map.on('rotate', () => { $('#north-rot').style.transform = `rotate(${-map.getBearing()}deg)`; });
  $('#north').onclick = () => map.resetNorth({ duration: 300 });
  $('#north').onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); map.resetNorth({ duration: 300 }); } };
  map.on('click', e => {
    if (!styleReady) return;
    const f = map.queryRenderedFeatures(e.point, { layers: ['dg-hit'] })[0];
    if (f) select(f.id, false); else if (S.sel >= 0 && !e.originalEvent.target.closest('#info')) select(-1);
  });
  map.on('mousemove', 'dg-hit', e => {
    const f = e.features && e.features[0]; if (!f) return;
    map.getCanvas().style.cursor = 'pointer';
    if (S.hover !== f.id) { if (S.hover >= 0) map.setFeatureState({ source: 'segs', id: S.hover }, { hv: 0 }); S.hover = f.id; map.setFeatureState({ source: 'segs', id: f.id }, { hv: 1 }); }
    showTip(f.id, e.point);
  });
  map.on('mouseleave', 'dg-hit', () => {
    map.getCanvas().style.cursor = ''; $('#tip').hidden = true;
    if (S.hover >= 0) { map.setFeatureState({ source: 'segs', id: S.hover }, { hv: 0 }); S.hover = -1; }
  });
  setBasemap(navigator.onLine === false ? 'none' : store.get('dg-basemap', S.theme === 'dark' ? 'dark' : 'light'), true);
}

function dataBounds() {
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  const idx = S.nb ? [...Array(N).keys()].filter(i => geo.features[i].properties.nb === S.nb) : null;
  for (let k = 0, n = idx ? idx.length : N; k < n; k++) { const b = bbox[idx ? idx[k] : k]; x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]); }
  return [[x0, y0], [x1, y1]];
}
function fitAll() { if (map) map.fitBounds(dataBounds(), { padding: 32, duration: 500 }); }

async function setBasemap(key, first) {
  S.basemap = key; if (!first) store.set('dg-basemap', key); renderBasemapUI();
  if (!map) return;
  let style;
  if (key === 'dark') {
    try { const r = await fetch(BASE[key].url); if (!r.ok) throw new Error(r.status); style = await r.json(); }
    catch (e) { if (!first) toast('Basemap unavailable offline, showing None'); else toast('Basemap tiles unavailable offline; showing None'); S.basemap = 'none'; renderBasemapUI(); style = BLANK(bgColor()); }
  } else style = key === 'osm' ? OSM : key === 'light' ? OSM_MUTED : BLANK(bgColor());
  styleReady = false;
  map.setStyle(style, { diff: false });
}

function firstSymbol() { const l = map.getStyle().layers.find(l => l.type === 'symbol'); return l && l.id; }

function onStyle() {
  for (const k in applied) delete applied[k];
  const before = firstSymbol();
  map.addSource('segs', { type: 'geojson', data: geo, maxzoom: 17, tolerance: 0.6, buffer: 32 });
  map.addSource('breaks', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  const L = (id, paint, extra) => map.addLayer(Object.assign({ id, type: 'line', source: 'segs', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint }, extra), before);
  L('dg-cond', { 'line-color': condColor, 'line-width': W(v => v ? v + 7 : 0), 'line-opacity': 0.8 });
  L('dg-shared', { 'line-color': '#7c3aed', 'line-width': W(v => v ? v + 9 : 0), 'line-opacity': ['case', ['==', st('sh', 0), 1], 0.6, 0] });
  L('dg-funded', { 'line-color': '#0e7490', 'line-width': W(v => v ? v + 5 : 0), 'line-opacity': ['case', ['==', st('fu', 0), 1], 0.7, 0] });
  L('dg-casing', { 'line-color': '#ffffff', 'line-width': W(v => v ? v * 1.35 + 1.4 : 0), 'line-opacity': 1 });
  L('dg-risk', { 'line-color': riskColor, 'line-width': W(v => v) });
  L('dg-plan', { 'line-color': ['match', st('pl', 0), 1, '#1d4ed8', 2, '#92400e', 3, '#111827', '#1d4ed8'], 'line-width': W(v => v ? Math.max(1, v * 0.4) : 0), 'line-dasharray': [2, 1.5], 'line-opacity': ['case', ['>', st('pl', 0), 0], 1, 0] });
  L('dg-hover', { 'line-color': '#111827', 'line-width': W(v => v ? v + 4 : 0), 'line-opacity': ['case', ['==', st('hv', 0), 1], 0.35, 0] });
  L('dg-sel-under', { 'line-color': '#0b2a6b', 'line-width': W(v => v ? v + 10 : 0) }, { filter: ['==', ['get', 'id'], ''] });
  L('dg-sel', { 'line-color': '#00e0ff', 'line-width': W(v => v ? v + 6 : 0) }, { filter: ['==', ['get', 'id'], ''] });
  L('dg-sel-core', { 'line-color': riskColor, 'line-width': W(v => v) }, { filter: ['==', ['get', 'id'], ''] });
  map.addLayer({ id: 'dg-breaks', type: 'circle', source: 'breaks', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 2.5, 13, 5, 17, 9], 'circle-color': '#111827', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2, 'circle-opacity': 1 } }, before);
  L('dg-hit', { 'line-color': '#000000', 'line-width': W(v => v ? Math.max(v + 6, 12) : 0), 'line-opacity': 0.005 });
  styleReady = true;
  applyLayerPrefs(); applyNbFilter(); applyBaseOpacity(); updateSelFilter(); renderState();
  const bgl = map.getStyle().layers.find(l => l.id === 'bg'); if (bgl) map.setPaintProperty('bg', 'background-color', bgColor());
}

const LAYER_IDS = { risk: ['dg-casing', 'dg-risk'], cond: ['dg-cond'], plan: ['dg-plan'], shared: ['dg-shared'], funded: ['dg-funded'], breaks: ['dg-breaks'] };
function applyLayerPrefs() {
  if (!styleReady) return;
  for (const k in LAYER_IDS) for (const id of LAYER_IDS[k]) {
    map.setLayoutProperty(id, 'visibility', S.layers[k] ? 'visible' : 'none');
    const f = S.op[k] / 100;
    if (id === 'dg-casing' || id === 'dg-risk') map.setPaintProperty(id, 'line-opacity', f);
    else if (id === 'dg-cond') map.setPaintProperty(id, 'line-opacity', 0.8 * f);
    else if (id === 'dg-shared') map.setPaintProperty(id, 'line-opacity', ['case', ['==', st('sh', 0), 1], 0.6 * f, 0]);
    else if (id === 'dg-funded') map.setPaintProperty(id, 'line-opacity', ['case', ['==', st('fu', 0), 1], 0.7 * f, 0]);
    else if (id === 'dg-plan') map.setPaintProperty(id, 'line-opacity', ['case', ['>', st('pl', 0), 0], f, 0]);
    else if (id === 'dg-breaks') { map.setPaintProperty(id, 'circle-opacity', f); map.setPaintProperty(id, 'circle-stroke-opacity', f); }
  }
}
const baseOrig = {};
function applyBaseOpacity() {
  if (!styleReady) return;
  const f = S.op.basemap / 100;
  const props = { background: ['background-opacity'], fill: ['fill-opacity'], line: ['line-opacity'], raster: ['raster-opacity'], symbol: ['icon-opacity', 'text-opacity'], circle: ['circle-opacity'], 'fill-extrusion': ['fill-extrusion-opacity'] };
  for (const l of map.getStyle().layers) {
    if (l.id.startsWith('dg-')) continue;
    for (const p of props[l.type] || []) {
      const key = l.id + p;
      if (!(key in baseOrig)) baseOrig[key] = map.getPaintProperty(l.id, p);
      const o = baseOrig[key];
      if (f >= 1) { if (o !== undefined) map.setPaintProperty(l.id, p, o); else map.setPaintProperty(l.id, p, 1); }
      else map.setPaintProperty(l.id, p, typeof o === 'number' || o === undefined ? (o === undefined ? 1 : o) * f : ['*', o, f]);
    }
  }
}
function applyNbFilter() {
  if (!styleReady) return;
  const base = S.nb ? ['==', ['get', 'nb'], S.nb] : null;
  for (const id of ['dg-cond', 'dg-shared', 'dg-funded', 'dg-casing', 'dg-risk', 'dg-plan', 'dg-hover', 'dg-hit']) map.setFilter(id, base);
  map.setFilter('dg-breaks', S.nb ? ['==', ['get', 'nb'], S.nb] : null);
}
function updateSelFilter() {
  if (!styleReady) return;
  const f = ['==', ['get', 'id'], S.sel >= 0 ? geo.features[S.sel].properties.id : ''];
  for (const id of ['dg-sel-under', 'dg-sel', 'dg-sel-core']) map.setFilter(id, f);
}

/* feature-state diffing: only segments whose class changed are touched */
function pushState(key, arr) {
  const old = applied[key] || (applied[key] = new Uint8Array(N).fill(255));
  const src = { source: 'segs' };
  for (let i = 0; i < N; i++) if (old[i] !== arr[i]) { src.id = i; map.setFeatureState(src, { [key]: arr[i] }); old[i] = arr[i]; }
}

function overlayArrays() {
  const pl = new Uint8Array(N), sh = new Uint8Array(N), fu = new Uint8Array(N);
  if (S.frame > 0) {
    const y = yearOf(S.frame), ph = S.playing ? S.phase : 4;
    if (ph >= 1) for (const [s, a] of y.plans) pl[s] = (a.includes('p') ? 1 : 0) + (a.includes('r') ? 2 : 0);
    if (ph >= 3) for (const d of y.funded) { fu[d[0]] = 1; if (d[3]) sh[d[0]] = 1; }
  }
  return { pl, sh, fu };
}

function renderState() {
  if (!bins[S.strategy]) return;
  const f = shownFrame();
  target.cls = plane(S.strategy, f, 'cls'); target.cond = plane(S.strategy, f, 'cond');
  Object.assign(target, overlayArrays());
  if (styleReady) {
    pushState('rc', target.cls); pushState('cc', target.cond); pushState('pl', target.pl); pushState('sh', target.sh); pushState('fu', target.fu);
    const ph = S.playing ? S.phase : 4;
    const feats = [];
    if (S.frame > 0 && ph >= 4) for (const [seg, cost] of yearOf(S.frame).failures) {
      const c = geo.features[seg].geometry.coordinates, p = c[Math.floor((c.length - 1) / 2)], q = c[Math.ceil((c.length - 1) / 2)];
      feats.push({ type: 'Feature', properties: { id: geo.features[seg].properties.id, seg, street: geo.features[seg].properties.street, cost, nb: geo.features[seg].properties.nb }, geometry: { type: 'Point', coordinates: [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2] } });
    }
    map.getSource('breaks').setData({ type: 'FeatureCollection', features: feats });
  }
  renderLegend(); renderKpis(); renderTimeline(); renderFeed(); renderInfo();
  if (curTab() === 'table') renderTable(); else tableDirty = true;
  if (curTab() === 'compare') renderCompare();
}

/* ---------- tooltips, selection ---------- */
function showTip(i, pt) {
  const p = geo.features[i].properties, t = $('#tip');
  t.innerHTML = `<b>${esc(p.street)}</b>${esc(p.id)}<br>Pipe risk: ${RISK[val('cls', i)][0]} (${val('risk', i)}), road ${COND[val('cond', i)][0]} <span style="opacity:.7">(simulated)</span>`;
  t.hidden = false;
  const w = $('#mapcol').clientWidth;
  t.style.left = Math.min(pt.x + 14, w - t.offsetWidth - 8) + 'px'; t.style.top = (pt.y + 14) + 'px';
}
function select(i, zoom) {
  S.sel = i; updateSelFilter(); renderInfo();
  if (i >= 0 && zoom) zoomTo(i);
  if (curTab() === 'table') renderTable(true);
}
function zoomTo(i) {
  if (!map) return;
  const b = bbox[i];
  map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 80, bottom: 80, left: 360, right: 80 }, maxZoom: 17.5, duration: 600 });
}
function renderInfo() {
  const box = $('#info');
  if (S.sel < 0) { box.hidden = true; return; }
  const i = S.sel, p = geo.features[i].properties, fr = shownFrame();
  const age = (meta.start_year + Math.max(0, fr - 1)) - val('inst', i, fr);
  const row = (k, v) => `<tr><th>${k}</th><td>${v}</td></tr>`;
  const sec = t => `<tr class="sec"><th colspan="2">${t}</th></tr>`;
  let plan = 'No data (baseline year)', fund = '', fundRows = '';
  if (S.frame > 0) {
    const L = lookups(S.frame), pa = L.plan.get(i), fd = L.funded.get(i), rj = L.rej.get(i), R = jsons[S.strategy].reasons;
    plan = pa ? 'Planned by ' + [...pa].map(c => AGENT[c]).join(' and ') : 'No plan posted';
    if (fd) fundRows = fd.map(d => row('Funded', `${AGENT[d[1]]} ${WORK[d[2]]}, ${fmtD(d[4])}${d[3] ? ', shared dig' : ''}<div class="muted reason">${esc(R[d[6]])}</div>`)).join('');
    else if (rj) fundRows = rj.slice(0, 3).map(d => row('Not funded', `${AGENT[d[1]]} ${WORK[d[2]]}<div class="muted reason">${esc(R[d[3]])}</div>`)).join('');
    else fundRows = row('Funding decision', 'No proposal this year');
  }
  box.innerHTML = `<header><h4>${esc(p.street)}<div class="muted" style="font-weight:400">${esc(p.id)} | ${esc(p.nb || '')}</div></h4><button class="icon" id="info-x" title="Close (Esc)" aria-label="Close feature info"><svg viewBox="0 0 16 16" width="12" height="12"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="1.6"/></svg></button></header>
  <table>${sec('Street (real)')}${row('Road class', esc(p.cls))}${row('Length', Math.round(p.len).toLocaleString() + ' ft')}
  ${sec('Pipe (simulated)')}${row('Material', MAT[val('mat', i, fr)])}${row('Install year', `${val('inst', i, fr)} (${age} yrs)`)}${row('Breaks on record', val('brk', i, fr))}${row('Risk class', `<span class="swatch" style="background:${RISK[val('cls', i, fr)][1]}"></span> ${RISK[val('cls', i, fr)][0]}`)}${row('Risk index', val('risk', i, fr))}
  ${sec('Road (simulated)')}${row('Condition', `<span class="swatch" style="background:${COND[val('cond', i, fr)][1]}"></span> ${COND[val('cond', i, fr)][0]} (rating ${val('pcr', i, fr)})`)}${row('Last paved', val('paved', i, fr))}${row('Traffic', p.adt.toLocaleString() + ' vehicles/day')}
  ${sec(S.frame > 0 ? 'This year (' + (meta.start_year + S.frame - 1) + ', simulated)' : 'This year')}${row('Plan status', plan)}${fundRows}</table>
  <footer><button class="text primary" id="info-zoom" title="Zoom the map to this segment">Zoom to feature</button><span class="muted">${esc(STRAT[S.strategy][0])}</span></footer>`;
  box.hidden = false;
  $('#info-x').onclick = () => select(-1);
  $('#info-zoom').onclick = () => zoomTo(i);
}

/* ---------- UI scaffolding ---------- */
function buildStaticUI() {
  const ss = $('#strategy'); meta.order.forEach(s => ss.appendChild(el('option', { value: s, textContent: STRAT[s][0] }))); ss.value = S.strategy;
  ss.onchange = async () => { S.strategy = ss.value; stop(); await loadStrategy(S.strategy); renderState(); };
  const nb = $('#nb'); meta.nbs.forEach(n => nb.appendChild(el('option', { value: n, textContent: n })));
  nb.onchange = () => { S.nb = nb.value; applyNbFilter(); renderState(); fitAll(); };
  const LL = [['risk', 'Pipe risk', 'Risk class by the team rubric'], ['cond', 'Road condition', 'Pavement condition rating'], ['plan', 'Repair plans', 'Segments an agent plans to dig (dashed)'], ['shared', 'Shared digs', 'Pipe and road work in one opening'], ['funded', 'Funded work', 'Work the budget agent funded this year'], ['breaks', 'Pipe breaks', 'Simulated breaks this year']];
  const ll = $('#layer-list');
  for (const [k, label, tip] of LL) {
    const d = el('div', { className: 'layer' }, `<label class="main" title="${esc(tip)}"><input type="checkbox" data-k="${k}" ${S.layers[k] ? 'checked' : ''}> <span>${label}</span></label>
      <div class="op"><span class="muted">Opacity</span><input type="range" min="0" max="100" value="${S.op[k]}" data-op="${k}" aria-label="${label} opacity"></div>`);
    ll.appendChild(d);
  }
  ll.addEventListener('change', e => { const k = e.target.dataset.k; if (k) { S.layers[k] = e.target.checked; applyLayerPrefs(); renderLegend(); } });
  ll.addEventListener('input', e => { const k = e.target.dataset.op; if (k) { S.op[k] = +e.target.value; applyLayerPrefs(); } });
  $('#op-basemap').oninput = e => { S.op.basemap = +e.target.value; applyBaseOpacity(); };
  const bm = $('#basemaps');
  for (const k in BASE) bm.appendChild(el('button', { type: 'button', role: 'radio', textContent: BASE[k].label, onclick: () => setBasemap(k) }));
  $('#btn-layers').onclick = () => { const c = $('#app').classList.toggle('no-layers'); $('#btn-layers').setAttribute('aria-expanded', !c); setTimeout(() => map && map.resize(), 30); };
  $('#btn-side').onclick = () => $('#app').classList.toggle('hide-side');
  if (innerWidth < 860) { $('#app').classList.add('no-layers'); $('#btn-layers').setAttribute('aria-expanded', 'false'); }
  $('#btn-theme').onclick = () => { setTheme(S.theme === 'dark' ? 'light' : 'dark'); if (S.basemap === 'light' || S.basemap === 'dark') setBasemap(S.theme === 'dark' ? 'dark' : 'light'); else if (S.basemap === 'none' && map) { const l = map.getStyle().layers.find(x => x.id === 'bg'); if (l) map.setPaintProperty('bg', 'background-color', bgColor()); } };
  $('#btn-png').onclick = exportPng; $('#btn-csv').onclick = exportCsv;
  $('#foot-scope').textContent = `Scope: ${meta.scope} (${N.toLocaleString()} segments, ${meta.miles} miles), seed ${meta.seed}.`;
  // timeline
  const ph = $('#phases'); PHASES.forEach((p, i) => ph.appendChild(el('div', { className: 'ph', textContent: p, id: 'ph' + i })));
  const sl = $('#slider'); sl.max = meta.frames - 1; sl.oninput = () => { const v = +sl.value; stop(); S.frame = v; S.phase = 4; renderState(); };
  const tk = $('#ticks'); for (let i = 0; i < meta.frames; i++) tk.appendChild(el('span', { textContent: i === 0 ? 'Start' : String(meta.start_year + i - 1), style: `left:${i / (meta.frames - 1) * 100}%` }));
  $('#b-play').onclick = togglePlay; $('#b-next').onclick = () => step(1); $('#b-prev').onclick = () => step(-1);
  $('#b-first').onclick = () => { stop(); S.frame = 0; S.phase = 4; renderState(); };
  $('#speed').onchange = e => { S.speed = +e.target.value; };
  // tabs
  $('#tabs').addEventListener('click', e => { const b = e.target.closest('button[data-tab]'); if (b) showTab(b.dataset.tab); });
  const ch = $('#chips'); for (const [a, l] of [['pipe', 'Pipe'], ['road', 'Road'], ['budget', 'Budget'], ['board', 'Board'], ['fail', 'Breaks']]) ch.appendChild(el('button', { className: 'chip', type: 'button', textContent: l, ariaPressed: 'true', title: 'Show or hide ' + l.toLowerCase() + ' events' })).dataset.a = a;
  ch.addEventListener('click', e => { const b = e.target.closest('.chip'); if (!b) return; const a = b.dataset.a; S.chips[a] = !S.chips[a]; b.setAttribute('aria-pressed', S.chips[a]); renderFeed(); });
  $('#feed').addEventListener('click', e => { const r = e.target.closest('.ev'); if (r && r.dataset.seg !== '') { select(+r.dataset.seg, true); } });
  buildSearch(); buildAbout(); buildTableHead();
  $('#tq').oninput = e => { S.tq = e.target.value.toLowerCase(); renderTable(); };
  $('#tscroll').addEventListener('scroll', () => drawRows());
  document.addEventListener('keydown', onKey);
  let wasNarrow = innerWidth < 860;
  window.addEventListener('resize', () => { const n = innerWidth < 860; if (n !== wasNarrow) { wasNarrow = n; $('#app').classList.toggle('no-layers', n); } if (map) map.resize(); });
}

function setTheme(t, initial) {
  S.theme = t; document.documentElement.setAttribute('data-theme', t); store.set('dg-theme', t);
}
function renderBasemapUI() { [...$('#basemaps').children].forEach((b, i) => b.setAttribute('aria-checked', Object.keys(BASE)[i] === S.basemap)); }
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 4000); }
function curTab() { const b = document.querySelector('#tabs [aria-selected="true"]'); return b && b.dataset.tab; }
let tableDirty = true;
function showTab(t) {
  document.querySelectorAll('#tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === t));
  document.querySelectorAll('.tabpane').forEach(p => { p.hidden = p.id !== 'tab-' + t; });
  if (t === 'table') renderTable(); if (t === 'compare') renderCompare();
}

/* ---------- legend, KPIs, timeline ---------- */
function renderLegend() {
  const lg = $('#legend'), counts = (arr, n) => { const c = new Array(n).fill(0); for (let i = 0; i < N; i++) if (!S.nb || nbIdx[i] === meta.nbs.indexOf(S.nb) + 1) c[arr[i]]++; return c; };
  const fr = shownFrame();
  $('#legend-year').textContent = fr === 0 ? '(baseline)' : '(' + (meta.start_year + fr - 1) + ')';
  const blk = (t, rows) => `<div class="legend-block"><div class="t">${t}</div>${rows.join('')}</div>`;
  const row = (sw, name, n) => `<div class="legend-row"><span class="swatch" style="${sw}"></span><span>${name}</span><span class="n">${n == null ? '' : n.toLocaleString()}</span></div>`;
  let h = '';
  if (S.layers.risk && target.cls) { const c = counts(target.cls, 4); h += blk('Pipe risk class (simulated)', [3, 2, 1, 0].map(i => row('background:' + RISK[i][1], RISK[i][0], c[i]))); }
  if (S.layers.cond && target.cond) { const c = counts(target.cond, 4); h += blk('Road condition (simulated)', [3, 2, 1, 0].map(i => row('background:' + COND[i][1], COND[i][0], c[i]))); }
  const ov = [];
  if (S.layers.plan && target.pl) { let a = 0; for (let i = 0; i < N; i++) if (target.pl[i] && (!S.nb || nbIdx[i] === meta.nbs.indexOf(S.nb) + 1)) a++; ov.push(row('background:transparent;border:0;width:12px;height:0;border-top:3px dashed #1d4ed8;border-radius:0', 'Planned dig', a)); }
  if (S.layers.shared && target.sh) { let a = 0; for (let i = 0; i < N; i++) if (target.sh[i]) a++; ov.push(row('background:#7c3aed', 'Shared dig', a)); }
  if (S.layers.funded && target.fu) { let a = 0; for (let i = 0; i < N; i++) if (target.fu[i]) a++; ov.push(row('background:#0e7490', 'Funded work', a)); }
  if (S.layers.breaks && S.frame > 0 && (!S.playing || S.phase >= 4)) ov.push(row('background:#111827;border-radius:50%', 'Pipe break', yearOf(S.frame).failures.length));
  if (ov.length) h += blk('Overlays (' + (S.frame > 0 ? 'this year' : 'none yet') + ')', ov);
  lg.innerHTML = h || '<div class="muted">No layers on.</div>';
}

function renderKpis() {
  const k = $('#kpis'), f = S.frame, ph = S.playing ? S.phase : 4;
  const card = (l, v, s) => `<div class="kpi"><div class="l">${l}</div><div class="v ${v == null ? 'empty' : ''}">${v == null ? 'Press Play to start' : v}</div><div class="s">${s || ''}</div></div>`;
  if (f === 0) { k.innerHTML = card('Funded work', null) + card('Shared digs', null) + card('Pipe breaks', null) + card('Spend', null); return; }
  const y = yearOf(f), m = y.metrics, pending = '--';
  const shared = new Set(y.funded.filter(d => d[3]).map(d => d[0])).size;
  const spend = y.funded.reduce((a, d) => a + d[4], 0);
  const yr = meta.start_year + f - 1;
  k.innerHTML = card('Funded work ' + yr, ph >= 3 ? y.funded.length : pending, ph >= 3 ? `${y.n_proposals} proposals, simulated` : 'pending') +
    card('Shared digs ' + yr, ph >= 3 ? shared : pending, 'one opening, two jobs') +
    card('Pipe breaks ' + yr, ph >= 4 ? y.failures.length : pending, `${m.fail} so far, simulated`) +
    card('Spend ' + yr, ph >= 3 ? fmtM(spend) : pending, `${fmtM(m.spend)} to date, simulated`);
}

function renderTimeline() {
  $('#slider').value = S.frame;
  const f = S.frame, ph = S.playing ? S.phase : 4;
  PHASES.forEach((_, i) => { const e = $('#ph' + i); e.className = 'ph' + (f === 0 ? '' : (S.playing ? (i === ph ? ' on' : i < ph ? ' done' : '') : ' done')); });
  $('#yearlabel').innerHTML = f === 0 ? `${meta.start_year}<small>Baseline, before any work</small>` : `${meta.start_year + f - 1}<small>Year ${f} of ${meta.frames - 1}${S.playing ? ': ' + PHASES[ph] : ''}</small>`;
  $('#b-play').setAttribute('aria-label', S.playing ? 'Pause' : 'Play');
  $('#ico-play').style.display = S.playing ? 'none' : ''; $('#ico-pause').style.display = S.playing ? '' : 'none';
}

/* ---------- playback ---------- */
function togglePlay() { S.playing ? stop() : play(); }
function play() {
  if (S.frame >= meta.frames - 1) { S.frame = 0; }
  S.playing = true; S.phase = S.frame === 0 ? 4 : S.phase;
  tick(true);
}
function stop() { S.playing = false; clearTimeout(timer); S.phase = 4; renderTimeline(); }
function tick(first) {
  if (!S.playing) return;
  if (first || S.phase >= 4) {
    if (S.frame >= meta.frames - 1 && !first) { S.playing = false; S.phase = 4; renderState(); return; }
    S.frame++; S.phase = 0;
  } else S.phase++;
  renderState();
  const last = S.frame >= meta.frames - 1 && S.phase >= 4;
  if (last) { S.playing = false; S.phase = 4; setTimeout(renderState, 0); return; }
  timer = setTimeout(() => tick(false), 800 / S.speed);
}
function step(d) { stop(); S.frame = Math.max(0, Math.min(meta.frames - 1, S.frame + d)); renderState(); }

/* ---------- feed ---------- */
const MSG_PHASE = m => m[2] === 'rating' ? 0 : (m[2] === 'funding_decision' ? 3 : (m[0] === 2 ? 2 : 1));
function renderFeed() {
  const feed = $('#feed');
  if (S.frame === 0) { feed.innerHTML = '<div class="empty-state">Press Play to start. Agent activity for each year appears here.</div>'; return; }
  const y = yearOf(S.frame), ph = S.playing ? S.phase : 4, ev = [];
  y.messages.forEach((m, k) => { const p = MSG_PHASE(m); if (p <= ph) ev.push({ k, p, a: m[1], seg: m[3], text: m[4] }); });
  if (ph >= 4) y.failures.forEach(([seg, cost], k) => { const g = geo.features[seg].properties; ev.push({ k: 1e6 + k, p: 4, a: 'fail', seg, text: `Simulated pipe break on ${g.street} (${g.id}); emergency repair and social cost ${fmtD(cost)}.` }); });
  ev.sort((a, b) => b.p - a.p || b.k - a.k);
  const shown = ev.filter(e => S.chips[e.a === 'fail' ? 'fail' : e.a]);
  const llm = S.strategy === 'coordinated_llm';
  const cap = 300;
  feed.innerHTML = (shown.length ? '' : '<div class="empty-state">No events match the filters.</div>') + shown.slice(0, cap).map(e =>
    `<div class="ev" data-seg="${e.seg == null ? '' : e.seg}" title="${e.seg == null ? '' : 'Zoom to this segment'}"><span class="who ${e.a}">${e.a === 'fail' ? 'Break' : e.a}</span><span class="txt">${llm && e.a !== 'board' && e.a !== 'fail' ? '<span class="llm">Claude</span>' : ''}${esc(e.text)}</span></div>`).join('') +
    (shown.length > cap ? `<div class="empty-state">Newest ${cap} of ${shown.length.toLocaleString()} events. Use the chips to narrow.</div>` : '');
}

/* ---------- table ---------- */
const COLS = [
  ['street', 'Street', i => geo.features[i].properties.street], ['id', 'Segment', i => geo.features[i].properties.id], ['nb', 'Neighborhood', i => geo.features[i].properties.nb || ''],
  ['cls', 'Class', i => geo.features[i].properties.cls], ['len', 'Length ft', i => Math.round(geo.features[i].properties.len)],
  ['risk', 'Pipe risk', i => val('risk', i)], ['rclass', 'Risk class', i => RISK[val('cls', i)][0], i => val('cls', i)],
  ['pcr', 'Road rating', i => val('pcr', i)], ['cond', 'Road condition', i => COND[val('cond', i)][0], i => val('cond', i)],
  ['mat', 'Material', i => MAT[val('mat', i)]], ['inst', 'Installed', i => val('inst', i)], ['brk', 'Breaks', i => val('brk', i)], ['paved', 'Last paved', i => val('paved', i)],
  ['adt', 'Vehicles/day', i => geo.features[i].properties.adt]];
let trows = [];
function buildTableHead() {
  const tr = $('#tbl thead').appendChild(el('tr'));
  COLS.forEach(c => { const th = el('th', { textContent: c[1], title: 'Sort by ' + c[1] }); th.dataset.c = c[0]; tr.appendChild(th); });
  tr.addEventListener('click', e => { const c = e.target.dataset.c; if (!c) return; S.sort = { col: c, dir: S.sort.col === c ? -S.sort.dir : 1 }; renderTable(); });
}
function renderTable(keepScroll) {
  tableDirty = false;
  const nbi = S.nb ? meta.nbs.indexOf(S.nb) + 1 : 0;
  const col = COLS.find(c => c[0] === S.sort.col) || COLS[0], key = col[3] || col[2];
  let idx = [];
  for (let i = 0; i < N; i++) {
    if (nbi && nbIdx[i] !== nbi) continue;
    if (S.tq) { const p = geo.features[i].properties; if (!(p.street.toLowerCase().includes(S.tq) || p.id.toLowerCase().includes(S.tq) || p.cls.includes(S.tq) || RISK[val('cls', i)][0].toLowerCase().includes(S.tq) || COND[val('cond', i)][0].toLowerCase().includes(S.tq))) continue; }
    idx.push(i);
  }
  const keys = new Map(idx.map(i => [i, key(i)]));
  idx.sort((a, b) => { const x = keys.get(a), y = keys.get(b); return (x < y ? -1 : x > y ? 1 : 0) * S.sort.dir; });
  trows = idx;
  $('#tcount').textContent = `${idx.length.toLocaleString()} of ${N.toLocaleString()}`;
  document.querySelectorAll('#tbl th').forEach(th => th.setAttribute('aria-sort', th.dataset.c === S.sort.col ? (S.sort.dir > 0 ? 'ascending' : 'descending') : 'none'));
  if (!keepScroll) $('#tscroll').scrollTop = 0;
  drawRows(true);
}
function drawRows() {
  const sc = $('#tscroll'), tb = $('#tbl tbody'), H = 28, top = Math.max(0, Math.floor(Math.max(0, sc.scrollTop - 32) / H) - 8), n = Math.ceil(sc.clientHeight / H) + 16;
  const end = Math.min(trows.length, top + n);
  let h = `<tr style="height:${top * H}px"><td colspan="${COLS.length}" style="padding:0;border:0"></td></tr>`;
  for (let r = top; r < end; r++) { const i = trows[r]; h += `<tr class="trow ${i === S.sel ? 'sel' : ''}" data-i="${i}">${COLS.map(c => `<td>${esc(c[2](i))}</td>`).join('')}</tr>`; }
  h += `<tr style="height:${Math.max(0, trows.length - end) * H}px"><td colspan="${COLS.length}" style="padding:0;border:0"></td></tr>`;
  tb.innerHTML = h;
}
$('#tbl').addEventListener('click', e => { const r = e.target.closest('tr.trow'); if (r) select(+r.dataset.i, true); });

/* ---------- compare ---------- */
const cum = s => [0].concat(jsons[s].years.map(y => y.metrics.spend + y.metrics.emerg + y.metrics.user_cost));
function renderCompare() {
  const t = $('#tab-compare'), ready = meta.order.filter(s => jsons[s]);
  if (ready.length < meta.order.length) { t.innerHTML = '<div class="empty-state">Loading all strategies...</div>'; return; }
  const f = S.frame, hdr = f === 0 ? 'Baseline: no work yet' : `Cumulative through ${meta.start_year + f - 1}`;
  const rows = meta.order.map(s => {
    const c = cum(s), m = f > 0 ? jsons[s].years[f - 1].metrics : null;
    return { s, c, m };
  });
  const best = f > 0 ? Math.min(...rows.map(r => r.c[f])) : null;
  const spark = (c, col) => { const w = 72, h = 22, mx = Math.max(...c) || 1; const pts = c.map((v, i) => `${(i / (c.length - 1) * w).toFixed(1)},${(h - 2 - v / mx * (h - 4)).toFixed(1)}`).join(' '); return `<svg width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/></svg>`; };
  let h = `<h5>Scoreboard (simulated). ${hdr}</h5><table class="score"><tr><th>Strategy</th><th>Total cost</th><th>Breaks</th><th>Dig savings</th><th>Trend</th></tr>` +
    rows.map(r => `<tr class="${r.s === S.strategy ? 'cur' : ''}"><td><span class="dot" style="background:${STRAT[r.s][1]}"></span>${esc(STRAT[r.s][0])}</td>
      <td style="${f > 0 && r.c[f] === best ? 'font-weight:600' : ''}">${f > 0 ? fmtM(r.c[f]) : '--'}</td><td>${r.m ? r.m.fail : '--'}</td><td>${r.m ? fmtM(r.m.dig_savings) : '--'}</td><td>${spark(r.c, STRAT[r.s][1])}</td></tr>`).join('') + '</table>';
  h += '<p class="muted">Total cost = capital + emergency repairs + road user cost. Lower is better. The central planner is a heuristic benchmark, not a proven upper bound.</p>';
  h += '<h5>Cumulative savings versus isolated departments</h5><div id="chart-wrap"></div>';
  t.innerHTML = h;
  drawChart($('#chart-wrap'));
}
function drawChart(host) {
  const W = 352, H = 232, m = { l: 48, r: 12, t: 12, b: 32 }, iso = cum('isolated');
  const series = meta.order.filter(s => s !== 'isolated').map(s => ({ s, v: cum(s).map((v, i) => (iso[i] - v) / 1e6) }));
  const all = series.flatMap(x => x.v), lo = Math.min(0, ...all), hi = Math.max(0.1, ...all);
  const nice = (a, b) => { const r = (b - a) / 4, p = Math.pow(10, Math.floor(Math.log10(r))), q = [1, 2, 5, 10].find(k => k * p >= r) * p; return [Math.floor(a / q) * q, Math.ceil(b / q) * q, q]; };
  const [y0, y1, dy] = nice(lo, hi), n = meta.frames - 1;
  const X = i => m.l + i / n * (W - m.l - m.r), Y = v => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  let g = '';
  for (let v = y0; v <= y1 + 1e-9; v += dy) g += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 6}" y="${Y(v) + 3}" text-anchor="end">${v.toFixed(v % 1 ? 1 : 0)}</text>`;
  for (let i = 0; i <= n; i++) g += `<text x="${X(i)}" y="${H - m.b + 14}" text-anchor="middle">${i === 0 ? 'Start' : String(meta.start_year + i - 1).slice(2)}</text>`;
  g += `<text x="${m.l}" y="${H - 4}" fill="currentColor">Year (start = baseline)</text><text transform="translate(12 ${(H - m.b) / 2 + 20}) rotate(-90)">Savings, $M (simulated)</text>`;
  const lines = series.map(x => `<polyline fill="none" stroke="${STRAT[x.s][1]}" stroke-width="2" ${x.s === 'central' ? 'stroke-dasharray="5 3"' : ''} points="${x.v.map((v, i) => X(i) + ',' + Y(v)).join(' ')}"/>`).join('');
  host.innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Cumulative savings versus isolated departments, by strategy">${g}${lines}<line id="cur-line" x1="${X(S.frame)}" x2="${X(S.frame)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--accent)" stroke-width="1" stroke-dasharray="3 3"/><line id="hov" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" visibility="hidden"/><rect id="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>
    <div class="row" style="flex-wrap:wrap;gap:8px 16px;margin-top:8px">${series.map(x => `<span><span class="dot" style="background:${STRAT[x.s][1]}"></span>${esc(STRAT[x.s][0])}</span>`).join('')}</div><div id="ctip" class="muted" style="min-height:40px;margin-top:8px"></div>`;
  const svg = $('svg', host), hit = $('#hit', host);
  hit.onmousemove = e => {
    const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * W, i = Math.max(0, Math.min(n, Math.round((x - m.l) / (W - m.l - m.r) * n)));
    const hv = $('#hov', host); hv.setAttribute('x1', X(i)); hv.setAttribute('x2', X(i)); hv.setAttribute('visibility', 'visible');
    $('#ctip', host).innerHTML = `<b style="color:var(--text)">${i === 0 ? 'Start' : meta.start_year + i - 1}</b><br>` + series.map(s => `${esc(STRAT[s.s][0])}: ${s.v[i] >= 0 ? '+' : ''}${s.v[i].toFixed(2)}M`).join(' &nbsp; ');
  };
  hit.onmouseleave = () => { $('#hov', host).setAttribute('visibility', 'hidden'); $('#ctip', host).innerHTML = ''; };
}

/* ---------- about ---------- */
function buildAbout() {
  $('#tab-about').innerHTML = `<div class="about"><div class="warnbox">ALL ASSET DATA SIMULATED. Only the street network is real.</div>
  <h5>What this is</h5><p>A prototype of three software agents (pipe, road, budget) that coordinate repairs on a shared board so a street is opened once, not several times. The replay shows each year: Rate, Plan, Negotiate, Fund, Apply.</p>
  <h5>Real versus simulated</h5><ul><li><b>Real:</b> street geometry, names, length, road class, neighborhood (Analyze Boston Street Segments, MassDOT Road Inventory).</li>
  <li><b>Simulated:</b> pipe material, install year, breaks, pavement condition, last paved, traffic, customers, costs, budget, every outcome.</li></ul>
  <h5>Strategies</h5><ul><li><b>Isolated departments:</b> separate budgets, no board.</li><li><b>Pooled budget:</b> one budget, no board (isolates the budget agent).</li><li><b>Agents + board:</b> agents negotiate shared digs (the proposal).</li><li><b>Central planner:</b> one planner with full data; a heuristic benchmark, not a proven upper bound.</li>${meta.order.includes('coordinated_llm') ? '<li><b>Agents + board (Claude):</b> the same flow with Claude writing the choices and rationale.</li>' : ''}</ul>
  <h5>Assumptions</h5><ul><li>Budget ${fmtD(meta.cfg.annual_capital_budget)} per year for this scope; about ${meta.cfg.n_target.toFixed(0)} pipe breaks per year expected at the start (per-mile assumptions).</li><li>Each agent proposes work on at most ${meta.cfg.max_proposals} segments a year.</li><li>Older pipes are assumed in older neighborhoods.</li><li>Risk class uses the team pipe rubric v2.0; road condition is a simplified age and traffic curve.</li></ul>
  <h5>Controls</h5><p class="muted">Space play or pause, Left and Right arrows change year, + and - zoom, F fits the network, L toggles the layer panel, Esc closes feature info.</p></div>`;
}

/* ---------- search ---------- */
function buildSearch() {
  const q = $('#q'), ul = $('#suggest'); let on = -1, cur = [];
  const go = n => { ul.hidden = true; q.value = n.n; let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9; n.ids.forEach(i => { const b = bbox[i]; x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]); }); if (map) map.fitBounds([[x0, y0], [x1, y1]], { padding: { top: 80, bottom: 80, left: 360, right: 80 }, maxZoom: 16.5, duration: 700 }); if (n.ids.length === 1) select(n.ids[0], false); };
  const draw = () => { const v = q.value.trim().toLowerCase(); if (!v) { ul.hidden = true; return; } cur = names.filter(n => n.l.startsWith(v)).concat(names.filter(n => !n.l.startsWith(v) && n.l.includes(v))).slice(0, 8); on = -1;
    ul.innerHTML = cur.map((n, i) => `<li role="option" data-i="${i}">${esc(n.n)} <span class="muted">${n.ids.length} seg</span></li>`).join('') || '<li class="muted">No street found</li>'; ul.hidden = false; };
  q.oninput = draw;
  q.onkeydown = e => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); on = Math.max(0, Math.min(cur.length - 1, on + (e.key === 'ArrowDown' ? 1 : -1))); [...ul.children].forEach((l, i) => l.classList.toggle('on', i === on)); } else if (e.key === 'Enter' && cur.length) go(cur[Math.max(0, on)]); else if (e.key === 'Escape') ul.hidden = true; };
  ul.onmousedown = e => { const li = e.target.closest('li[data-i]'); if (li) { e.preventDefault(); go(cur[+li.dataset.i]); } };
  q.onblur = () => { ul.hidden = true; };
}

/* ---------- export ---------- */
function download(name, blob) { const a = el('a', { href: URL.createObjectURL(blob), download: name }); document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function exportPng() {
  if (!map) return toast('The map is not available');
  map.once('render', () => {
    const c = map.getCanvas(), out = el('canvas'), pad = 28; out.width = c.width; out.height = c.height + pad;
    const x = out.getContext('2d'); x.drawImage(c, 0, 0); x.fillStyle = '#fff'; x.fillRect(0, c.height, out.width, pad); x.fillStyle = '#333'; x.font = '12px sans-serif';
    const fr = S.frame === 0 ? 'baseline' : String(meta.start_year + S.frame - 1);
    x.fillText(`Dig Once | ${STRAT[S.strategy][0]} | ${fr} | ALL ASSET DATA SIMULATED | streets: Analyze Boston, MassDOT`, 8, c.height + 18);
    out.toBlob(b => download(`dig-once-map-${S.strategy}-${fr}.png`, b));
  });
  map.triggerRepaint();
}
function exportCsv() {
  if (!trows.length || tableDirty) renderTable(true);
  const q = v => '"' + String(v).replace(/"/g, '""') + '"';
  const lines = [COLS.map(c => q(c[1])).join(',')].concat(trows.map(i => COLS.map(c => q(c[2](i))).join(',')));
  download(`dig-once-table-${S.strategy}-${S.frame === 0 ? 'baseline' : meta.start_year + S.frame - 1}.csv`, new Blob(['﻿' + lines.join('\n')], { type: 'text/csv' }));
}

/* ---------- keyboard ---------- */
function onKey(e) {
  if (e.target.matches('input, select, textarea') && e.key !== 'Escape') return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === ' ' && !e.target.closest('button')) { e.preventDefault(); togglePlay(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  else if (e.key === 'Home') { e.preventDefault(); $('#b-first').click(); }
  else if ((e.key === '+' || e.key === '=') && map) map.zoomIn();
  else if ((e.key === '-' || e.key === '_') && map) map.zoomOut();
  else if (e.key === 'f' || e.key === 'F') fitAll();
  else if (e.key === 'l' || e.key === 'L') $('#btn-layers').click();
  else if (e.key === 'Escape') { if (S.sel >= 0) select(-1); e.target.blur && e.target.blur(); }
}

window.__dig = { S, get map() { return map; }, select, zoomTo, setBasemap, renderState, get N() { return N; } };   // test hooks
boot();
})();
