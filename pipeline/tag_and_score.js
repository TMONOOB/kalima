// Run Kalima's own tagging code (compromise 14.14.4 + Kalima's classify/refine/lemma rules)
// over the extracted documents, score it against the hand-made UD labels, and write
// compact pre-tagged packs for the page.
//
// usage: node tag_and_score.js <kalima.js> <compromise.js> <docs.json> <outdir>
'use strict';
const fs = require('fs');
const path = require('path');
const [kalimaPath, nlpPath, docsPath, outDir, modelPath] = process.argv.slice(2);

// ---- load Kalima's tagging section verbatim ----
const js = fs.readFileSync(kalimaPath, 'utf8');
const a = js.indexOf('/* ---------------- tagging');
const b = js.indexOf('/* ---------------- corpus index');
if (a < 0 || b < 0) throw new Error('tagging section not found');
const section = js.slice(a, b);
const prelude = `
const NOUN=0,VERB=1,ADJ=2,ADV=3,PRON=4,PREP=5,DET=6,CONJ=7,NUM=8,OTHER=9;
const normWord = w => w.toLowerCase().replace(/[’‘]/g,"'");
const HAS_WORD = /[\\p{L}\\p{N}]/u;
`;
const factory = new Function('nlpLib', prelude + section + '\nNLP = nlpLib; taggerKind = "full";\nreturn {tagText, normWord, setModel: m => { MODEL = m; }, mLabelToKalima, ARTICLES, DEMONS, QUANTS, POSS_DET};');
const nlp = require(path.resolve(nlpPath));
const K = factory(nlp);
if (modelPath) K.setModel(JSON.parse(fs.readFileSync(modelPath, 'utf8')));
function mkLabel(g){ const [, , u, x, feats] = g; let pt = ''; if ((u==='PRON'||u==='DET'||u==='ADV') && /^(WP|WDT|WRB|WP\$)$/.test(x)) pt = /PronType=Rel/.test(feats) ? 'Rel' : /PronType=Int/.test(feats) ? 'Int' : ''; return u+':'+x+(pt?':'+pt:''); }

// ---- gold label -> Kalima's 10 word types (following Kalima's own guide) ----
const NAMES = ['noun','verb','adj','adv','pron','prep','det','conj','num','other'];
function goldClass(upos, xpos, feats){
  switch (upos){
    case 'NOUN': case 'PROPN': return 0;
    case 'VERB': case 'AUX': return 1;
    case 'ADJ': return /NumType=Ord/.test(feats) ? 8 : 2;      // "first" is a Number in Kalima
    case 'ADV': return 3;
    case 'PRON': return xpos === 'PRP$' ? 6 : 4;                // my/your/his = determiner in Kalima
    case 'ADP': return 5;
    case 'DET': return 6;
    case 'CCONJ': case 'SCONJ': return 7;
    case 'NUM': return 8;
    case 'INTJ': return 9;
    case 'PART':
      if (xpos === 'TO') return 1;                             // infinitive "to" = part of the verb (to-infinitive) in Kalima
      if (xpos === 'RB') return 3;                             // not / n't = adverb in Kalima
      return null;                                             // possessive 's is not a separate word in Kalima
    default: return null;                                      // PUNCT, SYM, X are not scored
  }
}

// ---- run ----
const data = JSON.parse(fs.readFileSync(docsPath, 'utf8'));
const codeTable = []; const codeIdx = new Map();
function codeOf(k){
  const key = k.p + '|' + k.d + '|' + k.tg;
  let c = codeIdx.get(key);
  if (c == null){ c = codeTable.length; codeIdx.set(key, c); codeTable.push([k.p, k.d, k.tg]); }
  return c;
}
const CODE_CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!$%&()*+,-./:;<=>?@[]^_`{|}~';
const escField = s => s.replace(/\\/g,'\\\\').replace(/\n/g,'\\n').replace(/\t/g,'\\t');

function newScore(){ return {n:0, ok:0, scorable:0}; }
const score = {};
const byGenre = {}; const bySplit = {};
const conf = {};                     // conf[col][gold][pred] = count
const confWords = {};                // `${g}>${p}` -> Map(word -> count)  (EWT only)
const perClass = {};   // col -> gold class -> {n, ok}
const predClass = {};  // col -> predicted class -> {n, ok}
const packs = {};
let alignMiss = 0; const totalKalimaWords = {};
const t0 = Date.now();

data.docs.forEach((d, di) => {
  const sents = K.tagText(d.text);
  // offsets of Kalima tokens
  let cur = 0; const spans = [];
  for (const s of sents) for (const k of s){
    const i = d.text.indexOf(k.w, cur);
    if (i < 0 || i - cur > 60){ spans.push(null); alignMiss++; continue; }
    spans.push([i, i + k.w.length, k]); cur = i + k.w.length;
  }
  const goldAt = new Map();
  for (const g of d.gold) if (g[0] >= 0) goldAt.set(g[0], g);
  // texts with hand-checked labels: show those labels (and base words) wherever a Kalima word matches a gold word exactly
  if (modelPath) for (const sp of spans){ if (!sp) continue; const g = goldAt.get(sp[0]); if (!g || g[1] !== sp[1]) continue; const k = sp[2], lw = K.normWord(k.w); const r = K.mLabelToKalima(mkLabel(g), lw); if (!r) continue; k.p = r.p; k.d = r.d; k.tg = r.tg; k.lm = (r.p===0 && r.d==='name') ? lw : String(g[5] || lw).toLowerCase(); if (k.p===6){ if (K.ARTICLES.has(lw)) k.d='article'; else if (K.DEMONS.has(lw)) k.d='demonstrative'; else if (K.POSS_DET.has(lw)){ k.d='possessive'; k.tg='PRP$'; } else if (K.QUANTS.has(lw)) k.d='quantifier'; } }
  const col = d.col; const S = score[col] = score[col] || newScore();
  perClass[col] = perClass[col] || {}; predClass[col] = predClass[col] || {};
  const gkey = col + ':' + d.genre;
  byGenre[gkey] = byGenre[gkey] || newScore();
  if (col === 'ewt'){ bySplit[d.split] = bySplit[d.split] || newScore(); }
  for (const g of d.gold){ if (goldClass(g[2], g[3], g[4]) != null){ S.scorable++; byGenre[gkey].scorable++; if (col==='ewt') bySplit[d.split].scorable++; } }
  for (const sp of spans){
    if (!sp) continue;
    const g = goldAt.get(sp[0]);
    if (!g || g[1] !== sp[1]) continue;                 // tokenisation differs: not scored
    const gc = goldClass(g[2], g[3], g[4]);
    if (gc == null) continue;
    const pc = sp[2].p; const ok = gc === pc;
    S.n++; S.ok += ok; byGenre[gkey].n++; byGenre[gkey].ok += ok;
    if (col === 'ewt'){ bySplit[d.split].n++; bySplit[d.split].ok += ok; }
    const pcs = perClass[col][gc] = perClass[col][gc] || {n:0, ok:0}; pcs.n++; pcs.ok += ok;
    const prs = predClass[col][pc] = predClass[col][pc] || {n:0, ok:0}; prs.n++; prs.ok += ok;
    conf[col] = conf[col] || {}; conf[col][gc] = conf[col][gc] || {}; conf[col][gc][pc] = (conf[col][gc][pc] || 0) + 1;
    if (!ok && col === 'ewt'){
      const key = gc + '>' + pc; const m = confWords[key] = confWords[key] || new Map();
      const w = K.normWord(sp[2].w); m.set(w, (m.get(w) || 0) + 1);
    }
  }
  // pack lines
  const lines = [];
  const meta = {id: d.id, title: d.title, type: d.type, region: d.region, source: d.source, lic: d.lic, licUrl: d.licUrl, col: d.col, genre: d.genre};
  if (d.url) meta.url = d.url;
  if (d.author) meta.author = d.author;
  let words = 0;
  const body = [];
  for (const s of sents){
    body.push('#S');
    for (const k of s){
      words++;
      const lw = K.normWord(k.w);
      const lm = k.lm === lw ? '' : k.lm;
      const pre = k.pre || '', post = k.post == null ? '' : k.post;
      const c = CODE_CHARS[codeOf(k)];
      let line = c + '\t' + escField(k.w);
      const postF = post === ' ' ? '' : (post === '' ? '\\_' : escField(post));
      if (pre || postF || lm) line += '\t' + escField(pre) + '\t' + postF + (lm ? '\t' + escField(lm) : '');
      body.push(line);
    }
  }
  meta.words = words; totalKalimaWords[col] = (totalKalimaWords[col] || 0) + words;
  lines.push('#D\t' + JSON.stringify(meta));
  (packs[col] = packs[col] || []).push(lines.concat(body).join('\n'));
  if (di % 200 === 0) process.stderr.write(`tagged ${di}/${data.docs.length} (${((Date.now()-t0)/1000).toFixed(0)}s)\n`);
});
if (codeTable.length > CODE_CHARS.length) throw new Error('too many tag codes: ' + codeTable.length);

// ---- write packs ----
fs.mkdirSync(outDir, {recursive: true});
for (const col of Object.keys(packs)){
  const head = '#KALIMA-PACK 1\t' + col + '\n#C\t' + JSON.stringify(codeTable) + '\n';
  fs.writeFileSync(path.join(outDir, col + '.txt'), head + packs[col].join('\n') + '\n');
}

// ---- results ----
const pct = (x, n) => n ? +(100 * x / n).toFixed(1) : null;
function topConfusions(col, limit){
  const rows = [];
  const C = conf[col] || {};
  for (const g in C) for (const p in C[g]) if (g !== p) rows.push({gold:+g, pred:+p, n:C[g][p]});
  rows.sort((x, y) => y.n - x.n);
  return rows.slice(0, limit).map(r => {
    const m = confWords[r.gold + '>' + r.pred];
    const ex = m ? Array.from(m.entries()).sort((x, y) => y[1] - x[1]).slice(0, 6).map(e => e[0]) : [];
    return {...r, goldName: NAMES[r.gold], predName: NAMES[r.pred], examples: ex};
  });
}
const result = {
  tagger: 'compromise 14.14.4 + Kalima rules (same code as the page)',
  ewt: {...score.ewt, acc: pct(score.ewt.ok, score.ewt.n), coverage: pct(score.ewt.n, score.ewt.scorable)},
  gum: {...score.gum, acc: pct(score.gum.ok, score.gum.n), coverage: pct(score.gum.n, score.gum.scorable)},
  ewtSplits: Object.fromEntries(Object.entries(bySplit).map(([k, v]) => [k, {...v, acc: pct(v.ok, v.n)}])),
  genres: Object.fromEntries(Object.entries(byGenre).map(([k, v]) => [k, {...v, acc: pct(v.ok, v.n)}])),
  ewtByClass: Object.fromEntries(Object.entries(perClass.ewt).map(([k, v]) => [NAMES[k], {...v, recall: pct(v.ok, v.n)}])),
  ewtByPred: Object.fromEntries(Object.entries(predClass.ewt).map(([k, v]) => [NAMES[k], {...v, precision: pct(v.ok, v.n)}])),
  ewtConfusions: topConfusions('ewt', 12),
  kalimaWords: totalKalimaWords, alignMiss, codes: codeTable.length,
  seconds: Math.round((Date.now() - t0) / 1000)
};
fs.writeFileSync(path.join(outDir, 'accuracy.json'), JSON.stringify(result, null, 1));
console.log(JSON.stringify(result, null, 1));
