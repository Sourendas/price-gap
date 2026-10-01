#!/usr/bin/env python3
"""Price Gap: compare Indian Google Shopping offers and highlight the cheapest in-stock price.

Reads SERPAPI_KEY from the environment or a local .env file. If it is missing, the server stays in
sample-data mode and never calls SerpApi. No key is embedded in this project.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_env_file() -> None:
    """Load .env from this folder. Existing environment variables win. Never logs values."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

load_env_file()
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8765"))
SEARCH_URL = "https://serpapi.com/search.json"
DEFAULT_LOCATION = "Bengaluru, Karnataka, India"
MAX_QUERY = 120
REQUEST_TIMEOUT = 35

OOS_RE = re.compile(
    r"out of stock|sold out|unavailable|not available|currently unavailable",
    re.IGNORECASE,
)
USED_RE = re.compile(r"\b(used|refurbished|pre-?owned|renewed|open box)\b", re.IGNORECASE)
INR_RE = re.compile(r"(₹|rs\.?|inr)", re.IGNORECASE)
USD_RE = re.compile(r"(\$|usd)", re.IGNORECASE)
NUMBER_RE = re.compile(r"(\d[\d,]*\.?\d*)")

SAMPLE_RETAILERS = [
    ("Flipkart", 26490, "in_stock", "new", "Free delivery"),
    ("Amazon.in", 26990, "in_stock", "new", "Free delivery tomorrow"),
    ("Vijay Sales", 27490, "in_stock", "new", "Store pickup in Bengaluru"),
    ("Croma", 28999, "in_stock", "new", "Free delivery"),
    ("Reliance Digital", 29990, "in_stock", "new", "Standard delivery"),
    ("Tata CLiQ", 27999, "out_of_stock", "new", "Out of stock"),
    ("Imagine", 24990, "out_of_stock", "new", "Sold out"),
    ("Cashify", 18499, "in_stock", "refurbished", "Refurbished"),
]


def has_api_key() -> bool:
    return bool(os.environ.get("SERPAPI_KEY", "").strip())


def redact(message: str) -> str:
    """Keep the private key out of UI errors and logs."""
    text = str(message)
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if key:
        text = text.replace(key, "[redacted]")
    return re.sub(r"(api_key=)[^&\s]+", r"\1[redacted]", text)


def format_inr(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    whole, frac = f"{value:.2f}".split(".")
    if frac == "00":
        frac = ""
    if len(whole) <= 3:
        grouped = whole
    else:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.append(head[-2:])
            head = head[:-2]
        if head:
            parts.append(head)
        grouped = ",".join(reversed(parts)) + "," + tail
    text = f"{sign}₹{grouped}"
    return f"{text}.{frac}" if frac else text


def _blob(item: dict) -> str:
    parts = [
        str(item.get("tag") or ""),
        str(item.get("badge") or ""),
        str(item.get("snippet") or ""),
        str(item.get("delivery") or ""),
        str(item.get("second_hand_condition") or ""),
        str(item.get("title") or ""),
    ]
    extensions = item.get("extensions") or []
    if isinstance(extensions, list):
        parts.extend(str(part) for part in extensions)
    return " ".join(parts)


def parse_price(item: dict) -> tuple[float | None, str, str]:
    """Return (amount, currency, display). Currency is INR, USD, or unknown."""
    raw = str(item.get("price") or "").strip()
    extracted = item.get("extracted_price")
    amount = None
    if isinstance(extracted, (int, float)) and not isinstance(extracted, bool) and extracted > 0:
        amount = float(extracted)
    elif raw:
        match = NUMBER_RE.search(raw.replace(" ", ""))
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
            except ValueError:
                amount = None
            if amount is not None and amount <= 0:
                amount = None
    if USD_RE.search(raw) and not INR_RE.search(raw):
        currency = "USD"
    elif INR_RE.search(raw) or (amount is not None and not USD_RE.search(raw)):
        # gl=in searches return local currency. A bare number is treated as INR.
        currency = "INR"
    else:
        currency = "unknown"
    if amount is None:
        return None, currency if raw else "unknown", raw
    display = raw or (format_inr(amount) if currency == "INR" else f"{amount:.2f}")
    return amount, currency, display


def condition_of(item: dict) -> str:
    explicit = str(item.get("second_hand_condition") or "").strip()
    if explicit:
        return explicit.lower()
    if USED_RE.search(_blob(item)):
        found = USED_RE.search(_blob(item))
        return found.group(1).lower().replace(" ", "-") if found else "used"
    return "new"


def stock_of(item: dict, amount: float | None) -> str:
    if OOS_RE.search(_blob(item)):
        return "out_of_stock"
    if amount is None:
        return "unpriced"
    return "in_stock"


def normalize_offer(item: dict, index: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").strip() or "Unknown retailer"
    if not title and not item.get("price") and not item.get("extracted_price"):
        return None
    amount, currency, display = parse_price(item)
    stock = stock_of(item, amount)
    condition = condition_of(item)
    link = item.get("link") or item.get("product_link") or ""
    rating = item.get("rating")
    reviews = item.get("reviews")
    return {
        "position": item.get("position") if item.get("position") is not None else index + 1,
        "title": title or "Untitled listing",
        "retailer": source,
        "price": amount,
        "currency": currency,
        "price_display": display if currency != "INR" or not amount else format_inr(amount),
        "stock": stock,
        "condition": condition,
        "in_stock": stock == "in_stock",
        "is_new": condition == "new",
        "rating": rating if isinstance(rating, (int, float)) else None,
        "reviews": reviews if isinstance(reviews, int) else None,
        "delivery": str(item.get("delivery") or "").strip(),
        "tag": str(item.get("tag") or "").strip(),
        "link": str(link),
        "thumbnail": str(item.get("thumbnail") or item.get("serpapi_thumbnail") or ""),
    }


def eligible(offer: dict, include_used: bool) -> bool:
    if not offer.get("in_stock"):
        return False
    if offer.get("currency") != "INR" or not offer.get("price"):
        return False
    if not include_used and not offer.get("is_new"):
        return False
    return True


def compare_offers(raw_results: list, include_used: bool = False) -> dict:
    offers = []
    for index, item in enumerate(raw_results or []):
        offer = normalize_offer(item, index)
        if offer:
            offers.append(offer)

    ranked = sorted(
        [offer for offer in offers if eligible(offer, include_used)],
        key=lambda offer: (offer["price"], offer.get("position") or 10**9, offer["retailer"].lower()),
    )

    by_retailer: dict[str, dict] = {}
    for offer in ranked:
        key = offer["retailer"].strip().lower()
        current = by_retailer.get(key)
        if current is None or offer["price"] < current["price"]:
            by_retailer[key] = offer
    retailer_rows = sorted(by_retailer.values(), key=lambda offer: (offer["price"], offer["retailer"].lower()))

    cheapest = retailer_rows[0] if retailer_rows else None
    runner = retailer_rows[1] if len(retailer_rows) > 1 else None
    highest = retailer_rows[-1] if retailer_rows else None
    gap = None
    if cheapest and runner:
        delta = round(runner["price"] - cheapest["price"], 2)
        base = runner["price"] or cheapest["price"]
        gap = {
            "versus": runner["retailer"],
            "amount": delta,
            "amount_display": format_inr(delta),
            "percent": round((delta / base) * 100, 1) if base else 0,
        }
    spread = None
    if cheapest and highest and highest is not cheapest:
        delta = round(highest["price"] - cheapest["price"], 2)
        spread = {
            "versus": highest["retailer"],
            "amount": delta,
            "amount_display": format_inr(delta),
        }

    hidden = [offer for offer in offers if not eligible(offer, include_used)]
    hidden.sort(key=lambda offer: ((offer.get("price") or 10**12), offer["retailer"].lower()))

    return {
        "cheapest": cheapest,
        "retailers": retailer_rows,
        "excluded": hidden,
        "gap_to_next": gap,
        "spread_to_highest": spread,
        "counts": {
            "listings": len(offers),
            "in_stock_compared": len(retailer_rows),
            "excluded": len(hidden),
        },
    }


def sample_payload(query: str, location: str, include_used: bool) -> dict:
    """Illustrative offers only. Not live Google Shopping prices."""
    shift = sum(ord(char) for char in query.lower()) % 17
    raw = []
    for index, (retailer, base, stock, condition, delivery) in enumerate(SAMPLE_RETAILERS):
        price = base + shift * 10 + (index * 13)
        tag = ""
        extensions = []
        if stock == "out_of_stock":
            tag = "Out of stock"
            extensions = ["Out of stock"]
        if condition != "new":
            extensions = extensions + ["Refurbished"]
        raw.append(
            {
                "position": index + 1,
                "title": query.strip(),
                "source": retailer,
                "price": format_inr(price),
                "extracted_price": price,
                "delivery": delivery,
                "tag": tag,
                "extensions": extensions,
                "second_hand_condition": None if condition == "new" else condition,
                "rating": 4.4 if condition == "new" else 4.1,
                "reviews": 1200 - index * 70,
                "link": "",
            }
        )
    compared = compare_offers(raw, include_used=include_used)
    return {
        "ok": True,
        "sample": True,
        "mode": "sample",
        "disclaimer": "Sample data. These prices are invented so the screen can run without an API key. They are not live retailer prices.",
        "query": query.strip(),
        "location": location,
        "engine": "google_shopping",
        "include_used": include_used,
        **compared,
    }


def live_search(query: str, location: str, include_used: bool) -> dict:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is not set")
    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": "in",
        "hl": "en",
        "google_domain": "google.co.in",
        "location": location,
        "device": "desktop",
        "api_key": key,
    }
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "PriceGap/1.0 (local hackathon app)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SerpApi returned a response that was not JSON") from exc
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = f"SerpApi returned HTTP {exc.code}"
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and parsed.get("error"):
                message = str(parsed["error"])
        except json.JSONDecodeError:
            pass
        raise RuntimeError(redact(message)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(redact(f"Could not reach SerpApi: {exc.reason}")) from exc
    except TimeoutError as exc:
        raise RuntimeError("SerpApi timed out") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(redact(str(payload["error"])))

    results = payload.get("shopping_results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        results = []
    metadata = payload.get("search_metadata") if isinstance(payload, dict) else {}
    compared = compare_offers(results, include_used=include_used)
    return {
        "ok": True,
        "sample": False,
        "mode": "live",
        "disclaimer": "Live Google Shopping results via SerpApi for India (google.co.in, gl=in). Cached repeats of the same search are free. This is the first page of offers Google returned, not every store in India.",
        "query": query.strip(),
        "location": location,
        "engine": "google_shopping",
        "include_used": include_used,
        "search_id": (metadata or {}).get("id"),
        **compared,
    }


def build_response(query: str, location: str, include_used: bool, force_sample: bool) -> dict:
    query = " ".join(query.split())
    location = " ".join(location.split()) or DEFAULT_LOCATION
    if not query:
        raise ValueError("Enter a product name.")
    if len(query) > MAX_QUERY:
        raise ValueError(f"Product name must be {MAX_QUERY} characters or fewer.")
    if len(location) > 120:
        raise ValueError("Location is too long.")
    if force_sample or not has_api_key():
        return sample_payload(query, location, include_used)
    return live_search(query, location, include_used)


class Handler(BaseHTTPRequestHandler):
    server_version = "PriceGap/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/status":
            live = has_api_key()
            self._json(
                200,
                {
                    "ok": True,
                    "has_key": live,
                    "mode": "live" if live else "sample",
                    "sample_available": True,
                    "engine": "google_shopping",
                    "country": "in",
                    "default_location": DEFAULT_LOCATION,
                },
            )
            return
        if path == "/":
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
        self._send(200, target.read_bytes(), types.get(target.suffix, "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/search":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > 8000:
            self._json(400, {"ok": False, "error": "Expected a small JSON body."})
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "Body must be JSON."})
            return
        if not isinstance(data, dict):
            self._json(400, {"ok": False, "error": "Body must be a JSON object."})
            return
        try:
            payload = build_response(
                str(data.get("query") or ""),
                str(data.get("location") or DEFAULT_LOCATION),
                bool(data.get("include_used")),
                bool(data.get("sample")),
            )
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        except RuntimeError as exc:
            self._json(502, {"ok": False, "error": str(exc), "mode": "live"})
            return
        self._json(200, payload)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    mode = "live SerpApi" if has_api_key() else "sample data (no SERPAPI_KEY)"
    print(f"Price Gap running at http://{HOST}:{PORT}  [{mode}]", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
