# book-index

The cloud half of the New Book Releases index. GitHub Actions collects from sources that don't need a sign-in, and commits what it finds to `data/`. Claude merges this with the browser-only sources (Edelweiss, Book Riot's New Release Index, Amazon) into the monthly master index and the weekly pages.

- `sources/publishers.csv`, `sources/authors.csv`: copies of the Publishers and Authors tabs of the "Book Index Sources" Sheet. Rows with `include` set to TRUE are collected. Claude refreshes these from the Sheet before each run.
- `collect.py probe`: reachability report for every source → `data/status.json`.
- `collect.py pw`: Publishers Weekly reviews (title, author, publisher, ISBN, pub month, starred) → `data/pw/reviews.json`, kept cumulatively by ISBN.
- `collect.py publishers` / `authors`: books listed on each site (JSON-LD first, then ISBN links) → `data/publishers/*.json`, `data/authors/*.json`, with a `_report.json` of what worked.

Schedule: every Monday (weekly sweep) and the 1st of each month (monthly master), plus "Run workflow" by hand.
