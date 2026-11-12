// Train Kalima's averaged-perceptron word-type model and score it on held-out text.
// usage: node --max-old-space-size=8192 train.js <page-script.js> <compromise.cjs> <docs_all.json> <out model.json> [iterations]
'use strict';
const fs = require('fs'), path = require('path');
const [pagePath, nlpPath, docsPath, outPath, itArg] = process.argv.slice(2);
const ITER = +(itArg || 7);
const js = fs.readFileSync(pagePath, 'utf8');
const section = js.slice(js.indexOf('/* ---------------- tagging'), js.indexOf('/* ---------------- corpus index'));
const prelude = `const NOUN=0,VERB=1,ADJ=2,ADV=3,PRON=4,PREP=5,DET=6,CONJ=7,NUM=8,OTHER=9;
const normWord = w => w.toLowerCase().replace(/[’‘]/g,"'"); const HAS_WORD = /[\\p{L}\\p{N}]/u;`;
const K = new Function('nlpLib', prelude + section + `
NLP = nlpLib; taggerKind = "full";
return {tagText, tagWithNlp, mFeats, normWord, setModel: m => { MODEL = m; }};`)(require(path.resolve(nlpPath)));

const data = JSON.parse(fs.readFileSync(docsPath, 'utf8')).docs.filter(d => d.gold && d.gold.length);
const isTrain = d => (d.col === 'ewt' || d.col === 'gum') && d.split === 'train';

function mkLabel(g){
  const [, , u, x, feats] = g;
  let pt = '';
  if ((u === 'PRON' || u === 'DET' || u === 'ADV') && /^(WP|WDT|WRB|WP\$)$/.test(x)) pt = /PronType=Rel/.test(feats) ? 'Rel' : /PronType=Int/.test(feats) ? 'Int' : '';
  return u + ':' + x + (pt ? ':' + pt : '');
}
// Training sentences: gold tokens with the rule tagger's first guess (cp) for words that start a Kalima token.
function sentencesOf(d){
  const raw = K.tagWithNlp(d.text.replace(/\r/g, ''));
  const startP = new Map(); let cur = 0;
  for (const s of raw) for (const k of s){ const i = d.text.indexOf(k.w, cur); if (i < 0 || i - cur > 60) continue; cur = i + k.w.length; startP.set(i, String(k.p)); }
  const bySent = new Map();
  for (const g of d.gold){ if (g[0] < 0) continue; const a = bySent.get(g[6]) || []; a.push(g); bySent.set(g[6], a); }
  const out = [];
  for (const gs of bySent.values()){
    let seenWord = false;
    out.push(gs.map(g => {
      const w = d.text.slice(g[0], g[1]);
      const isP = g[2] === 'PUNCT';
      const item = {w, lw: K.normWord(w), cp: isP ? '?' : (startP.get(g[0]) || '?'), cap: /^\p{Lu}/u.test(w), first: !isP && !seenWord, label: mkLabel(g)};
      if (!isP) seenWord = true;
      return item;
    }));
  }
  return out;
}

console.time('build');
const train = []; for (const d of data) if (isTrain(d)) train.push(...sentencesOf(d));
console.timeEnd('build');
const labels = Array.from(new Set(train.flatMap(s => s.map(x => x.label)))).sort();
const LI = new Map(labels.map((l, i) => [l, i]));
const nTok = train.reduce((a, s) => a + s.length, 0);
console.log('training sentences', train.length, 'tokens', nTok, 'labels', labels.length);

// tag dictionary: frequent words that nearly always get one label
const cnt = new Map();
for (const s of train) for (const x of s){ let m = cnt.get(x.w); if (!m){ m = new Map(); cnt.set(x.w, m); } m.set(x.label, (m.get(x.label) || 0) + 1); }
const td = {};
for (const [w, m] of cnt){ let n = 0, best = null, bn = 0; for (const [l, c] of m){ n += c; if (c > bn){ bn = c; best = l; } } if (n >= 20 && bn / n >= 0.97) td[w] = best; }
console.log('tag dictionary words', Object.keys(td).length);

class AP {
  constructor(n){ this.n = n; this.w = new Map(); this.acc = new Map(); this.i = 0; }
  predict(feats){
    const sc = new Float64Array(this.n);
    for (const f of feats){ const m = this.w.get(f); if (m) for (const [c, v] of m) sc[c] += v; }
    let b = 0; for (let c = 1; c < this.n; c++) if (sc[c] > sc[b]) b = c; return b;
  }
  upd(f, c, v){
    let m = this.w.get(f); if (!m){ m = new Map(); this.w.set(f, m); }
    let a = this.acc.get(f); if (!a){ a = new Map(); this.acc.set(f, a); }
    const w = m.get(c) || 0, st = a.get(c) || [0, 0];   // [total, last step]
    st[0] += (this.i - st[1]) * w; st[1] = this.i; a.set(c, st); m.set(c, w + v);
  }
  update(t, g, feats){ this.i++; if (t === g) return; for (const f of feats){ this.upd(f, t, 1); this.upd(f, g, -1); } }
  averaged(){
    const out = {};
    for (const [f, m] of this.w){
      const a = this.acc.get(f), arr = [];
      for (const [c, w] of m){ const st = a.get(c) || [0, 0]; const avg = (st[0] + (this.i - st[1]) * w) / this.i; if (Math.abs(avg) >= 0.005) arr.push(c, Math.round(avg * 1000) / 1000); }
      if (arr.length) out[f] = arr;
    }
    return out;
  }
}
let seed = 7; const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const ap = new AP(labels.length);
for (let it = 0; it < ITER; it++){
  let ok = 0, n = 0;
  for (let i = train.length - 1; i > 0; i--){ const j = Math.floor(rnd() * (i + 1)); [train[i], train[j]] = [train[j], train[i]]; }
  for (const s of train){
    let t1 = '<s>', t2 = '<s2>';
    for (let i = 0; i < s.length; i++){
      const x = s[i]; let g;
      if (td[x.w] != null) g = LI.get(td[x.w]);
      else { const feats = K.mFeats(s, i, t1, t2); g = ap.predict(feats); ap.update(LI.get(x.label), g, feats); }
      ok += labels[g] === x.label; n++; t2 = t1; t1 = labels[g];
    }
  }
  console.log(`iteration ${it + 1}: training-pass accuracy ${(100 * ok / n).toFixed(2)}%`);
}
const model = {v: 1, labels, w: ap.averaged(), td};
fs.writeFileSync(outPath, JSON.stringify(model));
console.log('model features', Object.keys(model.w).length, 'size', (fs.statSync(outPath).size / 1e6).toFixed(2) + 'MB');

// ---- held-out scoring through the page's own tagging code ----
K.setModel(model);
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
const N = ['noun','verb','adj','adv','pron','prep','det','conj','num','other'];
function score(docs){
  let n = 0, ok = 0, scorable = 0; const cls = {}, conf = new Map();
  for (const d of docs){
    const goldAt = new Map(d.gold.filter(g => g[0] >= 0).map(g => [g[0], g]));
    for (const g of d.gold) if (gc(g[2], g[3], g[4]) != null) scorable++;
    let cur = 0;
    for (const s of K.tagText(d.text)) for (const k of s){
      const i = d.text.indexOf(k.w, cur); if (i < 0 || i - cur > 60) continue; cur = i + k.w.length;
      const g = goldAt.get(i); if (!g || g[1] !== cur) continue;
      const G = gc(g[2], g[3], g[4]); if (G == null) continue;
      n++; ok += G === k.p; const c = cls[N[G]] = cls[N[G]] || [0, 0]; c[0]++; c[1] += G === k.p;
      if (G !== k.p){ const key = N[G] + ' -> ' + N[k.p]; const e = conf.get(key) || {n:0, w:new Map()}; e.n++; const lw = k.w.toLowerCase(); e.w.set(lw, (e.w.get(lw) || 0) + 1); conf.set(key, e); }
    }
  }
  return {n, ok, acc: +(100 * ok / n).toFixed(1), coverage: +(100 * n / scorable).toFixed(1),
    byClass: Object.fromEntries(Object.entries(cls).map(([k, [a, b]]) => [k, {n: a, recall: +(100 * b / a).toFixed(1)}])),
    confusions: Array.from(conf.entries()).sort((a, b) => b[1].n - a[1].n).slice(0, 12).map(([k, e]) => ({pair: k, n: e.n, examples: Array.from(e.w.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5).map(x => x[0])}))};
}
const sets = {
  ewt_test: data.filter(d => d.col === 'ewt' && d.split === 'test'),
  ewt_dev: data.filter(d => d.col === 'ewt' && d.split === 'dev'),
  gum_test: data.filter(d => d.col === 'gum' && d.split === 'test'),
  pud: data.filter(d => d.col === 'pud'),
};
const res = {};
for (const [k, docs] of Object.entries(sets)){ res[k] = score(docs); console.log(k, res[k].acc + '%', 'words', res[k].n, 'coverage', res[k].coverage + '%'); }
res.trainTokens = nTok;
res.trainWords = train.reduce((a, s) => a + s.filter(x => !x.label.startsWith('PUNCT')).length, 0);
res.date = new Date().toISOString().slice(0, 10);
fs.writeFileSync(outPath.replace(/\.json$/, '.scores.json'), JSON.stringify(res, null, 1));
console.log(JSON.stringify(res.ewt_test.byClass)); for (const c of res.ewt_test.confusions) console.log(c.n, c.pair, c.examples.join(', '));
