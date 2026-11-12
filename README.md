# Kalima Corpus

Kalima is a free, friendly English corpus for learners and teachers. It holds 1.13 million words of real
English. Every word shows its word type (noun, verb, adjective and so on) in plain English and Arabic,
with an explanation of why.

The whole site is a folder of ordinary files. Word types are worked out in each visitor's browser, so
Kalima needs no server, database or account to run, and it keeps working offline once it has loaded.

## What's in this repository

| Folder | What it holds |
| --- | --- |
| `site/` | The website itself: the page, data files, word-type model, icons and offline support. Publish this folder. |
| `site/data/` | The texts with their word types (`ewt.txt`, `gum.txt`, `pud.txt`, `books.txt`) and the model (`model.json`). Licences are in `site/data/LICENSES.md`. |
| `site/vendor/` | The compromise language library (MIT licence), served from the site so Kalima doesn't depend on another server. |
| `pipeline/` | The scripts that build the data files, train the model and write the names list. See `pipeline/README.md`. |
| `.github/workflows/pages.yml` | Publishes `site/` to GitHub Pages every time you push. |

## Putting it online

The site is ready as it is, so any static web host works. Two free options:

- **Cloudflare Pages** (works with a private repository): create a Pages project, connect this repository,
  leave the build command empty and set the output directory to `site`.
- **GitHub Pages** (free for public repositories): in the repository's settings, open Pages and choose
  GitHub Actions as the source. The included workflow then publishes `site/` on every push.

To use your own domain (for example `kalima.app`), buy it from a domain registrar, then add it in the
Pages settings of Cloudflare or GitHub and follow their instructions for the DNS records.

## Installing it on a phone

Kalima is a web app, so it installs straight from the website:

- **Android (Chrome):** open the site, open the menu and tap *Install app* or *Add to Home screen*.
- **iPhone (Safari):** open the site, tap *Share*, then *Add to Home Screen*.

It opens full screen with its own icon. After the first visit it works without a connection.

## Changing Kalima

- **Page, wording, colours, Arabic text:** edit `site/index.html`, then run
  `python3 -I pipeline/update_page.py site` so phones pick up the new version.
- **Texts, the model or the names list:** follow `pipeline/README.md`.

## Not included yet

"Add a text" and "Suggest a fix" are switched off. In the earlier claude.ai version they saved straight
into a shared store. A public site needs a server for that, and a review step so that copyrighted text,
spam or English with mistakes can't go straight into the corpus.

## Licences

- **Texts and model:** see `site/data/LICENSES.md`. The EWT, GUM and PUD texts and the model trained on
  them are under Creative Commons licences that allow commercial use with credit. Changed versions of the
  CC BY-SA material must be shared under the same licence. The books are in the public domain.
- **compromise library:** MIT licence, `site/vendor/compromise-LICENSE.txt`.
- **Names data:** `pipeline/names/pnbc` is CC0 (public domain); the lists in `pipeline/names/curated_*.txt`
  were written for Kalima.
- **Kalima's own code, design and wording:** © 2026 Tyab Mohammad, all rights reserved. See `LICENSE`.

This is a plain-language summary, not legal advice.

## How it was built

Kalima was designed by Tyab Mohammad. Much of the code, the word-type model and the accuracy tests were
written with the help of Claude, an AI assistant made by Anthropic.
