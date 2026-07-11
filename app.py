"""
A small Flask app that reads deals.csv (produced by scraper.py) and serves
an interactive dashboard: filter by genre and price, sort, and see the best
discounts highlighted.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"  # only needed for flash messages

CSV_PATH = os.path.join(os.path.dirname(__file__), "deals.csv")

# A deal at or above this discount gets a "Best Deal" badge.
BEST_DEAL_THRESHOLD = 50


def load_deals() -> list[dict]:
    """Read deals.csv into a list of dicts with proper types. Returns [] if missing."""
    if not os.path.exists(CSV_PATH):
        return []

    deals = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["price"] = float(row["price"]) if row["price"] not in ("", None) else 0.0
            except ValueError:
                row["price"] = 0.0
            try:
                row["original_price"] = float(row["original_price"]) if row["original_price"] not in ("", None) else None
            except ValueError:
                row["original_price"] = None
            try:
                row["discount_percent"] = int(float(row["discount_percent"])) if row["discount_percent"] not in ("", None) else 0
            except ValueError:
                row["discount_percent"] = 0
            row["in_bundle"] = str(row.get("in_bundle", "")).lower() == "true"
            row["is_best_deal"] = row["discount_percent"] >= BEST_DEAL_THRESHOLD
            deals.append(row)
    return deals


def last_scraped_label(deals: list[dict]) -> str:
    """Human-friendly 'last updated' string based on the most recent scraped_at."""
    timestamps = [d["scraped_at"] for d in deals if d.get("scraped_at")]
    if not timestamps:
        return "never"
    latest = max(timestamps)
    try:
        dt = datetime.fromisoformat(latest)
    except ValueError:
        return latest

    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(seconds // 86400)
    return f"{days} day{'s' if days != 1 else ''} ago"


@app.route("/")
def dashboard():
    all_deals = load_deals()
    all_genres = sorted({d["genre"] for d in all_deals if d.get("genre")})

    # read filters from query params
    selected_genres = request.args.getlist("genre")
    search = request.args.get("search", "").strip().lower()
    sort = request.args.get("sort", "discount_desc")

    def parse_float_arg(name, default):
        val = request.args.get(name, "")
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    max_possible_price = max([d["price"] for d in all_deals], default=100)
    min_price = parse_float_arg("min_price", 0)
    max_price = parse_float_arg("max_price", max_possible_price)

    # apply filters
    deals = all_deals
    if selected_genres:
        deals = [d for d in deals if d["genre"] in selected_genres]
    if search:
        deals = [d for d in deals if search in d["title"].lower() or search in d["developer"].lower()]
    deals = [d for d in deals if min_price <= d["price"] <= max_price]

    # sort
    sort_keys = {
        "discount_desc": (lambda d: d["discount_percent"], True),
        "price_asc": (lambda d: d["price"], False),
        "price_desc": (lambda d: d["price"], True),
        "title_asc": (lambda d: d["title"].lower(), False),
    }
    key_fn, reverse = sort_keys.get(sort, sort_keys["discount_desc"])
    deals = sorted(deals, key=key_fn, reverse=reverse)

    best_deal_count = sum(1 for d in all_deals if d["is_best_deal"])

    return render_template(
        "dashboard.html",
        deals=deals,
        total_count=len(all_deals),
        shown_count=len(deals),
        all_genres=all_genres,
        selected_genres=selected_genres,
        search=search,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        max_possible_price=max_possible_price,
        best_deal_count=best_deal_count,
        best_deal_threshold=BEST_DEAL_THRESHOLD,
        last_scraped=last_scraped_label(all_deals),
        has_data=len(all_deals) > 0,
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    """Re-run the scraper synchronously, then redirect back to the dashboard."""
    pages = request.form.get("pages", "3")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "scraper.py"),
             "--pages", pages, "--out", CSV_PATH],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            flash(f"Scrape failed: {result.stderr.strip()[-300:]}", "error")
        else:
            flash("Deals refreshed successfully.", "success")
    except subprocess.TimeoutExpired:
        flash("Scrape timed out. Try again or scrape fewer pages.", "error")
    except Exception as e:
        flash(f"Scrape failed: {e}", "error")

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
