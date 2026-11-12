# Rebuilding Kalima's data and model

Run this when you add texts, change the tagging rules in `site/index.html`, or edit the names lists.
It needs Python 3, Node.js 18 or newer, Git and about 12 GB of memory for training.
The Python scripts use only Python's standard library.

All commands run from the repository's top folder. Downloads go into `sources/` and working files into
`build/`. Neither folder is committed to Git (see `.gitignore`).

## 1. Download the source texts

```bash
mkdir -p sources/books build
git clone --depth 1 https://github.com/UniversalDependencies/UD_English-EWT sources/ewt
git clone --depth 1 https://github.com/amir-zeldes/gum sources/gum
git clone --depth 1 https://github.com/UniversalDependencies/UD_English-PUD sources/pud
for b in Pride-and-Prejudice_1342 The-Adventures-of-Sherlock-Holmes_1661 The-Adventures-of-Tom-Sawyer_74 \
         Anne-of-Green-Gables_45 The-Secret-Garden_113 Treasure-Island_120 Black-Beauty_271 \
         The-Wonderful-Wizard-of-Oz_55 The-Time-Machine_35 The-Call-of-the-Wild_215 The-Jungle-Book_236 \
         Alice-s-Adventures-in-Wonderland_11; do
  git clone --depth 1 https://github.com/GITenberg/$b sources/books/$b
done
```

To add a public-domain book, clone its GITenberg folder into `sources/books/` and add a line for it to
`BOOKS` in `pipeline/extract_more.py` (title, author, year first published, year the author died, region).

## 2. Turn the sources into Kalima texts

```bash
python3 -I pipeline/extract.py sources/ewt sources/gum/dep build/docs.json
python3 -I pipeline/extract_more.py sources/books sources/pud/en_pud-ud-test.conllu build/docs_more.json
python3 -I pipeline/merge_docs.py build/docs.json build/docs_more.json sources/gum/splits.md build/docs_all.json
```

`extract.py` keeps only the GUM genres whose licence allows commercial use (academic, court, news,
interview, bio, voyage) and drops the one court text taken from the Santa Barbara Corpus.

## 3. Train the word-type model and test it

```bash
node --max-old-space-size=12000 pipeline/train.js site/index.html pipeline/compromise-14.14.4.cjs build/docs_all.json build/model.json 7
node pipeline/prune_eval.js site/index.html pipeline/compromise-14.14.4.cjs build/docs_all.json build/model.json 0.5
cp build/model.p0.5.json site/data/model.json
```

`train.js` learns from the training parts of EWT and GUM only, then scores the model on EWT's test part,
GUM's test texts and PUD, which it never sees. The scores go to `build/model.scores.json`.
`prune_eval.js` drops the smallest weights so the model file stays about 4 MB, and prints the scores again.

## 4. Tag every text and write the data files

```bash
node --max-old-space-size=8000 pipeline/tag_and_score.js site/index.html pipeline/compromise-14.14.4.cjs build/docs_all.json build/packs site/data/model.json
cp build/packs/ewt.txt build/packs/gum.txt build/packs/books.txt build/packs/pud.txt site/data/
```

Texts with hand-checked labels (EWT, GUM, PUD) keep the linguists' labels; the books are labelled by the model.

## 5. Names list, page figures and offline version

```bash
python3 -I pipeline/build_names.py pipeline/names site
python3 -I pipeline/update_page.py site build
```

`build_names.py` writes the names list into `site/index.html`. `update_page.py` writes the new accuracy
figures, word count and book list into the page, then gives the offline cache a new name so phones
download the new version. Run `python3 -I pipeline/update_page.py site` after any hand edit to the site too.

## Checking the tagger

```bash
node pipeline/analyze.js site/index.html pipeline/compromise-14.14.4.cjs build/docs_all.json --model site/data/model.json --examples 3
```

lists the most common mix-ups with examples, and how often Kalima's base words match the linguists'.
It covers all of EWT, including the training part, so its accuracy runs higher than the test score in step 3.
