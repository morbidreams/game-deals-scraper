# ‧₊˚ ☁️⋅♡⋅☾⋅☁️ ˚₊‧ Game Deals Scraper ‧₊˚ ☁️⋅♡⋅☾⋅☁️ ˚₊‧

Scrapes live discounts from the [Steam store](https://store.steampowered.com/search/?specials=1)
with `requests` + `BeautifulSoup`, saves them to a CSV, and serves them in a dark-themed Flask
dashboard with genre/price filters and best-deal highlighting.

```
scraper.py            -> fetches Steam, writes deals.csv
app.py                -> Flask app that reads deals.csv and serves the dashboard
templates/dashboard.html
deals.csv              -> included with 3 SAMPLE rows so you can preview the UI immediately
requirements.txt
```

## Setup

```bash
python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

## 1. Scrape real data

The included `deals.csv` has 3 sample/fake games just so there's something to show the first time you open it. Replace it with the real thing:

```bash
python scraper.py                       # 2 pages per genre (~50 games each) into deals.csv
python scraper.py --pages 1             # faster, fewer results
python scraper.py --genres Action RPG   # only scrape specific genres
python scraper.py --pages 1 --debug     # saves the raw HTML it fetched, for troubleshooting
```

This takes a while the first time (11 genres × pages, ~1.5s pause between requests). Use `--genres` to narrow it down if you don't need the full sweep.

## 2. Run the dashboard

```bash
python app.py
```

Open **http://127.0.0.1:5000**. You can also click **"Refresh deals"** in the header to re-run the scraper from inside the browser (it calls `scraper.py` for you, 3 pages/genre).

## How the scraper works

Steam's search results page (`store.steampowered.com/search/?specials=1`) is server-rendered HTML. A plain `requests.get()` returns the full result list, no headless browser needed. Each game sits inside an `<a class="search_result_row">`, from which the scraper pulls:

- title & store URL (the row's own link and text)
- price + discount % (`.discount_final_price`, `.discount_original_price`, `.discount_pct`)
- release date and thumbnail image

It checks `robots.txt` before scraping, identifies itself with a real User-Agent, and forces
`cc=us&l=english` so prices/currency and text stay consistent regardless of where you run it.

**Steam's Subscriber Agreement** has general language against automated data collection.
Scraping the public search page at a light, deliberately-throttled rate (as this script does)
is extremely common for hobby/research projects, but it's worth knowing this sits on
different footing than a site that explicitly welcomes it.

## Features

- **Filters**: search by title, genre (multi-select), min/max price
- **Sort**: biggest discount, price low→high, price high→low, title A→Z
- **Best Deal badge**: any game discounted 50%+ gets a badge (change
  `BEST_DEAL_THRESHOLD` in `app.py` to adjust)
- Every card links out to the real Steam store page

## Customizing

- **Different genre set**: edit `DEFAULT_GENRES` in `scraper.py`, or pass `--genres` at the
  command line.
- **Top sellers instead of specials**: Steam's search also supports other filters. You could
  add `&category1=998` (Games only, excludes DLC/software) to `fetch_page()`'s params.
- **Best deal threshold**: `BEST_DEAL_THRESHOLD` in `app.py`.
- **Auto-refresh on a schedule**: instead of clicking the button, you could cron a call to
  `python scraper.py` every hour.
