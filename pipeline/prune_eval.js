// Prune small weights from the model and re-score EWT test / PUD through the page's tagging code.
'use strict';
const fs = require('fs'), path = require('path');
const [pagePath, nlpPath, docsPath, modelPath, ...ths] = process.argv.slice(2);
const js = fs.readFileSync(pagePath, 'utf8');
const section = js.slice(js.indexOf('/* ---------------- tagging'), js.indexOf('/* ---------------- corpus index'));
const prelude = `const NOUN=0,VERB=1,ADJ=2,ADV=3,PRON=4,PREP=5,DET=6,CONJ=7,NUM=8,OTHER=9;
const normWord = w => w.toLowerCase().replace(/[’‘]/g,"'"); const HAS_WORD = /[\\p{L}\\p{N}]/u;`;
const K = new Function('nlpLib', prelude + section + '\nNLP = nlpLib; taggerKind="full"; return {tagText, setModel: m => { MODEL = m; }};')(require(path.resolve(nlpPath)));
const gc = (u,x,f) => ({NOUN:0,PROPN:0,VERB:1,AUX:1,ADJ:/NumType=Ord/.test(f)?8:2,ADV:3,PRON:x==='PRP$'?6:4,ADP:5,DET:6,CCONJ:7,SCONJ:7,NUM:8,INTJ:9,PART:x==='TO'?1:x==='RB'?3:null})[u] ?? null;
const docs = JSON.parse(fs.readFileSync(docsPath,'utf8')).docs;
const sets = {ewt_test: docs.filter(d=>d.col==='ewt'&&d.split==='test'), pud: docs.filter(d=>d.col==='pud')};
const full = JSON.parse(fs.readFileSync(modelPath,'utf8'));
for (const T of ths.map(Number)){
  const w = {};
  for (const [f, arr] of Object.entries(full.w)){ const a = []; for (let i=0;i<arr.length;i+=2) if (Math.abs(arr[i+1]) >= T) a.push(arr[i], Math.round(arr[i+1]*100)/100); if (a.length) w[f] = a; }
  const m = {v:1, labels:full.labels, w, td:full.td}; const out = modelPath.replace(/\.json$/, `.p${T}.json`);
  fs.writeFileSync(out, JSON.stringify(m)); K.setModel(m);
  const r = {};
  for (const [k, ds] of Object.entries(sets)){ let n=0, ok=0; for (const d of ds){ const goldAt = new Map(d.gold.filter(g=>g[0]>=0).map(g=>[g[0],g])); let cur=0;
    for (const s of K.tagText(d.text)) for (const kk of s){ const i=d.text.indexOf(kk.w,cur); if(i<0||i-cur>60) continue; cur=i+kk.w.length; const g=goldAt.get(i); if(!g||g[1]!==cur) continue; const G=gc(g[2],g[3],g[4]); if(G==null) continue; n++; ok+=G===kk.p; } }
    r[k] = (100*ok/n).toFixed(2)+'%'; }
  console.log('threshold', T, 'features', Object.keys(w).length, 'size', (fs.statSync(out).size/1e6).toFixed(2)+'MB', JSON.stringify(r));
}
