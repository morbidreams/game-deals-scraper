"""
Scrapes discounted games from the Steam store search page
(https://store.steampowered.com/search/?specials=1) using requests +
BeautifulSoup, and writes the results to a CSV file that the Flask
dashboard (app.py) reads from.

Why this endpoint? It's the same HTML search page Steam's own site uses,
it's server-rendered (no JS needed to see results), and /search/ is NOT
disallowed in Steam's robots.txt (only account/checkout/email paths are).
"""

import argparse
import csv
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://store.steampowered.com/search/"
ROBOTS_URL = "https://store.steampowered.com/robots.txt"

# Steam's own canonical genre categories (these match the "genre=" values
# Steam's search page itself uses — see the sidebar filters on the site).
DEFAULT_GENRES = [
    "Action", "Adventure", "Casual", "Indie", "RPG", "Simulation",
    "Strategy", "Sports", "Racing", "Massively Multiplayer", "Free to Play",
]

HEADERS = {
    "User-Agent": "GameDealsScraperBot/1.0 (personal project)"
}

REQUEST_TIMEOUT = 15


def check_robots_allowed(url: str) -> bool:
    """Ask the site's robots.txt whether we're allowed to fetch `url`."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(ROBOTS_URL)
    try:
        rp.read()
    except Exception:
        print("Could not read robots.txt. Aborting to be safe.")
        return False
    return rp.can_fetch(HEADERS["User-Agent"], url)


def fetch_page(session: requests.Session, genre: str, page: int) -> str | None:
    """Fetch one page of discounted games for a given genre."""
    params = {
        "specials": 1,
        "genre": genre,
        "page": page,
        "cc": "us",       # force US region so prices/currency are consistent
        "l": "english",   # force English so text parsing is consistent
    }
    try:
        resp = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  ! Failed to fetch {genre!r} page {page}: {e}")
        return None


def _extract_amount(el) -> float | None:
    """Pull a decimal amount like '$9.99' -> 9.99 out of a price element."""
    if el is None:
        return None
    text = el.get_text(strip=True)
    if not text:
        return None
    if text.lower() in ("free", "free to play"):
        return 0.0
    m = re.search(r"(\d[\d,]*\.\d{2})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def parse_row(row, genre: str) -> dict | None:
    """Pull structured data out of a single `a.search_result_row` element."""
    store_url = row.get("href", "").split("?")[0]
    appid = row.get("data-ds-appid")
    if not store_url or not appid:
        return None

    title_el = row.find("span", class_="title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    released_el = row.find("div", class_="search_released")
    release_date = released_el.get_text(strip=True) if released_el else ""

    discount_pct_el = row.find("div", class_="discount_pct")
    discount_percent = 0
    if discount_pct_el:
        m = re.search(r"(\d{1,3})", discount_pct_el.get_text(strip=True))
        if m:
            discount_percent = int(m.group(1))

    current_price = _extract_amount(row.find("div", class_="discount_final_price"))
    if current_price is None:
        # Not part of a discount block (shouldn't normally happen on a
        # specials-only search, but fall back just in case).
        current_price = _extract_amount(row.find("div", class_="search_price"))
    if current_price is None:
        current_price = 0.0

    original_price = _extract_amount(row.find("div", class_="discount_original_price"))

    img_el = row.find("img")
    thumb_url = img_el.get("src") if img_el else None

    return {
        "title": title,
        "developer": "",  # not shown on the search results list
        "genre": genre,
        "price": current_price,
        "original_price": original_price if original_price is not None else "",
        "discount_percent": discount_percent,
        "in_bundle": False,
        "description": f"Released {release_date}" if release_date else "",
        "thumbnail_url": thumb_url or "",
        "store_url": store_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def parse_page(html: str, genre: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("a", class_="search_result_row")
    games = []
    for row in rows:
        try:
            game = parse_row(row, genre)
            if game:
                games.append(game)
        except Exception as e:
            print(f"  ! Skipped one row due to a parse error: {e}")
    return games


def scrape(genres: list[str], pages_per_genre: int, delay: float, debug: bool) -> list[dict]:
    if not check_robots_allowed(SEARCH_URL):
        print(f"robots.txt disallows scraping {SEARCH_URL}. Stopping.")
        sys.exit(1)

    session = requests.Session()
    all_games: list[dict] = []
    seen_urls: set[str] = set()

    for genre in genres:
        print(f"\nGenre: {genre}")
        for page in range(1, pages_per_genre + 1):
            print(f"  Page {page}/{pages_per_genre}...")
            html = fetch_page(session, genre, page)
            if html is None:
                continue

            if debug:
                debug_path = f"debug_{genre.replace(' ', '_').lower()}_page_{page}.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"    (saved raw HTML to {debug_path})")

            games = parse_page(html, genre)
            if not games:
                print("    No games found — this genre is exhausted, moving on.")
                break

            new_count = 0
            for g in games:
                if g["store_url"] not in seen_urls:
                    seen_urls.add(g["store_url"])
                    all_games.append(g)
                    new_count += 1
            print(f"    Found {len(games)} games ({new_count} new).")

            time.sleep(delay)  # be polite between requests

    return all_games


def write_csv(games: list[dict], out_path: str):
    fieldnames = [
        "title", "developer", "genre", "price", "original_price",
        "discount_percent", "in_bundle", "description", "thumbnail_url",
        "store_url", "scraped_at",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(games)


def main():
    parser = argparse.ArgumentParser(description="Scrape discounted games from Steam into a CSV file.")
    parser.add_argument("--pages", type=int, default=2, help="Search result pages to scrape PER GENRE (default: 2, ~50 games each)")
    parser.add_argument("--genres", nargs="+", default=DEFAULT_GENRES, help="Which genres to scrape (default: a standard Steam genre set)")
    parser.add_argument("--out", type=str, default="deals.csv", help="Output CSV path (default: deals.csv)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between requests (default: 1.5)")
    parser.add_argument("--debug", action="store_true", help="Save raw HTML of each fetched page for inspection")
    args = parser.parse_args()

    print(f"Starting scrape of {SEARCH_URL} (genres: {', '.join(args.genres)})...")
    games = scrape(args.genres, args.pages, args.delay, args.debug)

    if not games:
        print("\nNo games scraped. Nothing written.")
        sys.exit(1)

    write_csv(games, args.out)
    print(f"\nDone. Wrote {len(games)} unique deals to {args.out}")


if __name__ == "__main__":
    main()
