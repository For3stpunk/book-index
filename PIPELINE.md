# Book Index pipeline (for Claude's scheduled runs)

Two scheduled tasks drive this. Each starts a fresh session, so everything it needs is here, in this repo, or in the artifacts listed below.

- **Monthly master** (1st of each month): build the master index for the month after next (on Dec 1, build February).
- **Weekly sweep** (Mondays): re-collect, add anything new to the current and next month's masters, and publish a page for the coming week.

## Where things live

| What | Where |
| --- | --- |
| Source registry (the user edits it) | Sheet "Book Index Sources — Publishers & Authors", artifact `8e59b22d-aba6-41f8-a97b-726ed581741b`. Tabs: Publishers, Core sources, Authors. Read and write it with the Claude Docs connector (`guide` topic.sheets first). |
| Cloud collectors | this repo, `collect.py`, run by `.github/workflows/collect.yml` (Run workflow with `what` = probe, discover, pw, publishers, authors, all). Results in `data/`. |
| Site build scripts | `site/`: `build.py` (Edelweiss raw → books.json + desc shards), `merge.py REPO_DIR` (adds PW + publisher sites), `variant.py NAME START END TITLE H1 LEDE SPRITEMAP` (writes `out/NAME/index.html` + `desc/*.json`; set `MERGED=books_merged.json`), `template.html`, `foot.html`. |
| Relay (browser → workspace, and cover sheets) | artifact "Book Finder Import Relay" `1d14dc03-e77f-4716-b61d-85df59de496f` (`site/relay.html`). Its assets hold the Edelweiss JSON pulls and the cover sprite sheets. Keep private data (Edelweiss descriptions) here, never in this public repo. |
| Published pages | Main finder `e288d45e-5390-4422-9c1d-a0cc34108d40`; Dec 2026 `6da285ea-fb11-4d86-b37b-45d574f8a9ad`; Jan 2027 `e4c14525-69e0-4416-82da-203c60dcb4e7`; week of Nov 24 `4d0ef235-cc16-4561-9747-f4cec8d9ba64`; week of Dec 1 `0390d8e9-23cf-4c77-8818-06f89d21b014`. New month/week pages: publish_files, then declare_capabilities `{"assets": {}, "downloads": true}`. |
| Daily Roundup book beats ("In the news") | repo For3stpunk/daily-roundup, `data/*.json`, topics book-news / book-releases / book-reviews. |

## Monthly master, step by step

1. **Sync the registry.** Read the Publishers and Authors tabs; write `sources/publishers.csv` and `sources/authors.csv` (rows with Include ticked); commit and push.
2. **Cloud collection.** Dispatch the workflow with `what=all` (REST: `gh api -X POST repos/For3stpunk/book-index/actions/workflows/collect.yml/dispatches -f ref=main -f 'inputs[what]=all'`), wait for it, `git pull`. Write `data/publishers/_report.json` results back to the Sheet's Last checked / Notes columns.
3. **Edelweiss (needs the user's Chrome, signed in).** In an edelweiss.plus tab:
   - Catalog list: on Catalogs → Newly Added → All Publishers with the time frame "In Last Year", `window.items` holds every catalog id. Set the time frame back to "In Last 3 Months" afterwards.
   - Titles per catalog: `POST /api/list-views/items` with `{"pageProperties":{"resultType":31,"itemType":1,"listId":<catalogId>,"listSku":null,"itemsPerPage":50,"searchQuery":null,"startDateAdded":null},"sortProperties":{"overrideSortColumn":1,"overrideSortDirection":0},"filterProperties":{"hasFiltersSelected":false,"filteredListItemIds":[],"showHidden":false}}` → `unfilteredListItemIds`.
   - Pub dates: `POST api/v2/products/product?apiView=standard` with up to 100 skus; keep those in the target month.
   - Details: `POST api/v2/products/images,categories,contributors,audienceRanges,product?apiView=standard` and `POST api/v2/products/descriptions?apiView=standard,advanced` (50 skus each). Keep sku, ean, name, subName, contributorsWithType, supplier, pubDate, format, pages, BISAC categories, audience, language, status, jacketCover uri, summary or keynotes.
   - Run the loops in the background inside the page (store progress on `window`), poll with short calls, save the result to IndexedDB `bookfinder`/`kv`, then send it through the relay: open the relay artifact, press "Open Edelweiss sender", and from that new tab `postMessage({type:'bfchunk', name, text})` to `window.opener`, waiting for each `bfack`. Read the assets back with read_asset.
   - The site is flaky: 503s on first load, and a reload fixes broken page scripts. The extension's output filter blocks strings with `= & ?`, so replace those characters in anything you return.
4. **Covers.** Press "Open cover sender" in the relay (it opens an images-azf.edelweiss.plus tab). Ask the relay for the list (`bflist`, served from `covlist.json`, which you publish to the relay first: one `PUB|file.jpg` per book with a cover, in books.json order). Draw 100 covers per 1200×1800 JPEG sheet (10×10 cells of 120×180) and send each as `bfchunk` with a `blob`. Keep the relay tab in front: in a background tab its uploads stall. Then `copy_asset` the sheets into each page that needs them, and pass a sprite map (`{"sheets":[["/_blob/<id>",rows]|null,…],"miss":{}}`) to variant.py.
5. **Book Riot** comes from the cloud collector (`collect.py bookriot`: public posts found through the WordPress API, cumulative in `data/bookriot/mentions.json`, matched by ISBN or title + author; each match links to the posts). The user has no All Access membership, so skip the New Release Index. **Amazon** "Hot New Releases" needs a normal browser (Chrome); if unreachable, say so in the summary and carry on.
6. **Build.** In `site/`: put the Edelweiss pull in `raw.json` and the Daily Roundup book items in `feed_items.json`; run `START=YYYY-MM-01 END=YYYY-MM-31 python3 build.py`, then `python3 merge.py ..`, then `MERGED=books_merged.json python3 variant.py <name> …`. Test the page locally with Playwright before publishing.
7. **Publish** the month page (new artifact for a new month) and update the main finder. Send the user a short summary: counts by source, anything that failed, links.

## Weekly sweep

1. Steps 1–2 above with `what=all`.
2. If Chrome is available: Amazon (step 5). Book Riot is already in the cloud collection.
3. Merge into the current and next month's masters (step 6) and republish them.
4. Publish a page for the coming week (Monday–Sunday), named "New Book Releases — Week of <Tuesday's date>", with the covers it needs.
5. Summary to the user: what was new this week, by source.

## Known gaps (Nov 24, 2026)

- Kirkus: discover pages are built in the browser and froze Chrome; `/search/books/?q=` is server-rendered and readable from GitHub, so a per-title lookup is the likely route.
- PW category pages only go back four pages (about 40 reviews each), so the PW file grows week by week rather than reaching far back.
- Publisher sites that block GitHub's servers (S&S, Macmillan, Bloomsbury, Kensington, Candlewick, Sourcebooks) rely on Edelweiss.
