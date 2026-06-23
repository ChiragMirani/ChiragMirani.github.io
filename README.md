# The Vedas in English

Static GitHub Pages reader for public-domain English translations of the four Veda Samhitas: Rigveda, Samaveda, Yajurveda, and Atharvaveda.

Live site target: https://chiragmirani.github.io/vedas/

## What It Includes

- 4 Vedas, 52 books, and 2,251 passages.
- Searchable reader with Veda, book, and passage navigation.
- Verse-by-verse English translation display.
- Plain meaning line for each verse, generated from the English translation.
- Inferred event/use relevance for every passage.
- Sanskrit and IAST transliteration where an aligned source is attached.
- Source attribution for every passage.
- PWA metadata, app icons, Open Graph image, sitemap, robots.txt, and llms.txt.

## Sources

- Rigveda: Ralph T.H. Griffith translation, 1896, via SanskritWeb public-domain PDF.
- Samaveda: Ralph T.H. Griffith translation, 1895, via Sacred Texts.
- Yajurveda: Arthur Berriedale Keith translation of the Taittiriya Samhita, 1914, via Sacred Texts.
- Atharvaveda: Ralph T.H. Griffith translation, 1895-1896, via Sacred Texts.
- Original-language text: aligned GRETIL IAST e-texts for Rigveda and Atharvaveda where available. Devanagari is generated from the IAST text. Samaveda and Yajurveda original-language fields are marked source-needed until an aligned source can be attached safely.

The Vedas are traditionally received as shruti. Translator/source labels identify the English editions used for this digital reader, not authorship of the Vedas themselves.

Event/use labels are inferred from passage titles and English translations for study. Ritual usage varies by tradition, recension, and lineage.

## SEO And AEO

The static site follows current search basics:

- Descriptive page titles and meta descriptions.
- Canonical URLs for the reader and source page.
- Open Graph and Twitter card metadata.
- JSON-LD structured data for `WebSite`, `CreativeWork`, `AboutPage`, and visible FAQ-style answers.
- Crawlable `robots.txt` and `sitemap.xml`.
- Visible answer-style content on the homepage for common Veda questions.
- `llms.txt` with canonical URLs, source notes, and machine-readable context.
- Crawlable visible text covering Sanskrit/transliteration availability and inferred event relevance.

Google's current guidance for AI Overviews and AI Mode says standard SEO fundamentals still apply: crawlability, helpful visible text, internal links, page experience, textual content, and structured data that matches visible page content.

## Build

Regenerate the dataset:

```powershell
python .\scripts\fetch_vedas.py
```

Run the audit:

```powershell
python .\scripts\fetch_vedas.py --audit
```

Regenerate icons and social assets:

```powershell
python .\scripts\fetch_vedas.py --assets
```

Serve locally:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

## Deployment

The generated `docs/` directory is copied to the `vedas/` folder of the `ChiragMirani.github.io` GitHub Pages repository.
