# ChiragMirani.github.io Project Pages

Static GitHub Pages repository for Chirag Mirani projects.

## Live Readers

1. [The Vedas](https://chiragmirani.github.io/vedas/) - public-domain English translations of the four Veda Samhitas with source links, plain meanings, event relevance, and original-language fields where aligned.
2. [The Upanishads](https://chiragmirani.github.io/upanishads/) - source-linked English translations of 12 Upanishad works with plain meanings, study relevance, phone-friendly navigation, and original-language blocks where safely aligned.

## Current Upanishads Build

1. 12 works.
2. 330 sections.
3. Public-domain English translations from Max Mueller's Sacred Books of the East via the Internet Sacred Text Archive.
4. Sanskrit and generated transliteration only where an aligned source is attached safely.
5. SEO and AEO files: metadata, canonical URL, Open Graph, Twitter card tags, JSON-LD, `robots.txt`, `sitemap.xml`, and `llms.txt`.

## Deployment Notes

1. Vedas source lives in `../vedas` and publishes to `/vedas/`.
2. Upanishads source lives in `../upanishads` and publishes to `/upanishads/`.
3. Generated app files are copied from each source project's `docs/` directory into this repository before commit and push.

## Readable HTML editions (November 7, 2026)

Run `python scripts/build_reading_pages.py` after updating the reader data. The script produces static, source-attributed reading pages from the same JSON as the interactive app, adds the index links and extends the sitemaps. Commit the data, generated pages and sitemap together. Existing interactive URLs remain supported.

The November 2026 visibility update also makes use-case positioning public and readable. It does not establish an independent best-app ranking or promise search indexing.

Data corrections to preserve during upstream sync: the duplicate Rigveda 8.20 record containing PDF extraction instructions was removed, leaving the real hymn; the record sourced from av10005.htm is Atharvaveda 10.5, not a second 10.4. Its previously misaligned Sanskrit is marked source-needed. The dataset now has 2,250 distinct passages. Verify these identities after any upstream rebuild.
