// Error analysis of Kalima's tagging against the gold UD labels (EWT and GUM):
// accuracy, the biggest confusions with in-context examples, and lemma agreement.
// usage: node analyze.js <page-script.js> <compromise.cjs> <docs.json> [--examples N] [--json out.json]
'use strict';
const fs = require('fs'), path = require('path');
const args = process.argv.slice(2);
const [kalimaPath, nlpPath, docsPath] = args;
const nEx = args.includes('--examples') ? +args[args.indexOf('--examples') + 1] : 0;
const jsonOut = args.includes('--json') ? args[args.indexOf('--json') + 1] : null;
const modelPath = args.includes('--model') ? args[args.indexOf('--model') + 1] : null;
const js = fs.readFileSync(kalimaPath, 'utf8');
const section = js.slice(js.indexOf('/* ---------------- tagging'), js.indexOf('/* ---------------- corpus index'));
const prelude = `const NOUN=0,VERB=1,ADJ=2,ADV=3,PRON=4,PREP=5,DET=6,CONJ=7,NUM=8,OTHER=9;
const normWord = w => w.toLowerCase().replace(/[’‘]/g,"'"); const HAS_WORD = /[\\p{L}\\p{N}]/u;`;
const K = new Function('nlpLib', prelude + section + '\nNLP = nlpLib; taggerKind="full"; return {tagText, setModel: m => { MODEL = m; }};')(require(path.resolve(nlpPath)));
if (modelPath) K.setModel(JSON.parse(fs.readFileSync(modelPath, 'utf8')));
const N = ['noun','verb','adj','adv','pron','prep','det','conj','num','other'];
function gc(u, x, f){
  switch (u){
    case 'NOUN': case 'PROPN': return 0; case 'VERB': case 'AUX': return 1;
    case 'ADJ': return /NumType=Ord/.test(f) ? 8 : 2; case 'ADV': return 3;
    case 'PRON': return x === 'PRP$' ? 6 : 4; case 'ADP': return 5; case 'DET': return 6;
    case 'CCONJ': case 'SCONJ': return 7; case 'NUM': return 8; case 'INTJ': return 9;
    case 'PART': return x === 'TO' ? 1 : x === 'RB' ? 3 : null;
    default: return null;
  }
}
const data = JSON.parse(fs.readFileSync(docsPath, 'utf8'));
const S = {ewt:[0,0], gum:[0,0]}; const conf = {}; const ex = {}; const lem = {n:0, ok:0, miss:new Map()};
const genre = {};
for (const d of data.docs){
  const goldAt = new Map(d.gold.filter(g => g[0] >= 0).map(g => [g[0], g]));
  let cur = 0; const toks = [];
  for (const s of K.tagText(d.text)) for (const k of s){
    const i = d.text.indexOf(k.w, cur); if (i < 0 || i - cur > 60) continue; cur = i + k.w.length; toks.push([i, cur, k]);
  }
  for (const [a, b, k] of toks){
    const g = goldAt.get(a); if (!g || g[1] !== b) continue;
    const G = gc(g[2], g[3], g[4]); if (G == null) continue;
    const ok = G === k.p; S[d.col][0]++; S[d.col][1] += ok;
    const gk = d.col + ':' + d.genre; genre[gk] = genre[gk] || [0,0]; genre[gk][0]++; genre[gk][1] += ok;
    if (d.col !== 'ewt') continue;
    if (!ok){
      const key = N[G] + ' -> ' + N[k.p]; const c = conf[key] = conf[key] || {n:0, words:new Map()}; c.n++;
      const w = k.w.toLowerCase(); c.words.set(w, (c.words.get(w) || 0) + 1);
      if (nEx && (ex[key] = ex[key] || []).length < nEx) ex[key].push(d.text.slice(Math.max(0, a - 40), a).replace(/\s+/g, ' ') + '[[' + k.w + ']]' + d.text.slice(b, b + 30).replace(/\s+/g, ' '));
    } else if (G <= 3 && g[5]){
      lem.n++; const gl = g[5].toLowerCase(), kl = (k.lm || '').toLowerCase();
      if (gl === kl || G === 0 && k.d === 'name') lem.ok++;
      else { const key = k.w.toLowerCase() + ': ' + kl + ' (gold ' + gl + ')'; lem.miss.set(key, (lem.miss.get(key) || 0) + 1); }
    }
  }
}
const pct = ([n, ok]) => (100 * ok / n).toFixed(2) + '%';
console.log('EWT', pct(S.ewt), S.ewt.join('/'), '  GUM', pct(S.gum), S.gum.join('/'));
console.log('genres', Object.entries(genre).map(([k, v]) => k + ' ' + pct(v)).join(', '));
const rows = Object.entries(conf).sort((a, b) => b[1].n - a[1].n);
for (const [k, c] of rows.slice(0, 30)){
  console.log(String(c.n).padStart(5), k.padEnd(16), Array.from(c.words.entries()).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([w, n]) => w + ':' + n).join(' '));
  if (nEx && ex[k]) for (const e of ex[k]) console.log('        ', e);
}
console.log('LEMMA agreement on correctly typed nouns/verbs/adjs/advs:', (100 * lem.ok / lem.n).toFixed(2) + '%', lem.ok + '/' + lem.n);
console.log(Array.from(lem.miss.entries()).sort((a, b) => b[1] - a[1]).slice(0, 40).map(([k, n]) => n + ' ' + k).join('\n'));
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify({ewt:S.ewt, gum:S.gum}));
