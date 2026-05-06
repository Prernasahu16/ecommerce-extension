# ============================================================
# EXTENSION LAYER — Multi-Source Data Connectors
# FILE: backend/services/connectors.py
# PURPOSE: Adapters for Amazon, Flipkart, and FakeStore that
#          pull product data and feed it into data_pipeline.ingest().
#          Does NOT interfere with existing scraper/scraper.py logic.
# ============================================================

import logging
import os
import requests

log = logging.getLogger(__name__)

TIMEOUT = int(os.getenv("EXT_SCRAPE_TIMEOUT", 15))


# -------------------------------------------------------
# CONNECTOR BASE
# -------------------------------------------------------
class BaseConnector:
    """All connectors return a list of raw dicts consumable by data_pipeline."""
    source: str = "unknown"
    country: str = "US"

    def fetch(self, query: str = "", limit: int = 40) -> list[dict]:
        raise NotImplementedError


# -------------------------------------------------------
# CONNECTOR 1: FakeStore API  (free public API — safe for dev)
# Maps FakeStore fields → canonical raw dict
# -------------------------------------------------------
class FakeStoreConnector(BaseConnector):
    source  = "fakestore"
    country = "US"

    def fetch(self, query: str = "", limit: int = 40) -> list[dict]:
        log.info(f"[FakeStoreConnector] Fetching products (query={query!r})")
        try:
            resp = requests.get(
                "https://fakestoreapi.com/products",
                timeout=TIMEOUT
            )
            resp.raise_for_status()
            products = resp.json()
        except Exception as e:
            log.error(f"[FakeStoreConnector] Fetch error: {e}")
            return []

        raw = []
        for p in products[:limit]:
            raw.append({
                "id":           str(p.get("id", "")),
                "product_name": p.get("title", ""),
                "price":        p.get("price", 0),
                "original_price": round(float(p.get("price", 0)) * 1.2, 2),
                "rating":       p.get("rating", {}).get("rate", 0),
                "reviews":      p.get("rating", {}).get("count", 0),
                "category":     p.get("category", "General"),
                "image_url":    p.get("image", ""),
                "product_url":  f"https://fakestoreapi.com/products/{p.get('id')}",
            })

            # Filter by query string if provided
            if query and query.lower() not in (p.get("title", "") + p.get("category", "")).lower():
                raw.pop()

        log.info(f"[FakeStoreConnector] Returning {len(raw)} products")
        return raw


# -------------------------------------------------------
# CONNECTOR 2: Amazon (mock adapter)
# In production: replace _mock_fetch with real ScrapeOps/
# RapidAPI call.  The pipeline contract is unchanged.
# -------------------------------------------------------
class AmazonConnector(BaseConnector):
    source  = "amazon"
    country = "US"

    def fetch(self, query: str = "electronics", limit: int = 20) -> list[dict]:
        log.info(f"[AmazonConnector] Fetching query={query!r} country={self.country}")
        return self._mock_fetch(query, limit)

    def _mock_fetch(self, query: str, limit: int) -> list[dict]:
        """
        Stub implementation — returns realistic mock data.
        Replace the body of this method with your preferred
        Amazon API / scraping library without changing callers.
        """
        import random, hashlib

        seed   = hashlib.md5(f"amazon:{query}".encode()).hexdigest()
        random.seed(seed)

        categories_map = {
            "electronics": ["Laptop", "Bluetooth Speaker", "Wireless Headphones",
                            "Mechanical Keyboard", "USB-C Hub", "Smart Watch"],
            "fashion":     ["Running Shoes", "Leather Wallet", "Sunglasses",
                            "Casual Jacket", "Sports Cap", "Yoga Pants"],
            "home":        ["Air Purifier", "Coffee Maker", "Blender",
                            "Vacuum Cleaner", "LED Desk Lamp", "Throw Pillow"],
        }
        key  = query.lower().split()[0] if query else "electronics"
        pool = categories_map.get(key, categories_map["electronics"])

        products = []
        for i, name in enumerate(pool[:limit]):
            price    = round(random.uniform(15, 800), 2)
            orig     = round(price * random.uniform(1.05, 1.60), 2)
            rating   = round(random.uniform(3.0, 5.0), 1)
            reviews  = random.randint(50, 15000)
            products.append({
                "id":           f"amz-{seed[:8]}-{i}",
                "product_name": f"{name} ({query.title()})",
                "price":        price,
                "original_price": orig,
                "rating":       rating,
                "reviews":      reviews,
                "category":     key.title(),
                "image_url":    f"https://via.placeholder.com/200?text={name.replace(' ', '+')}",
                "product_url":  f"https://www.amazon.com/dp/B{seed[:9].upper()}{i}",
            })
        return products


# -------------------------------------------------------
# CONNECTOR 3: Flipkart (mock adapter — India, INR→USD)
# -------------------------------------------------------
class FlipkartConnector(BaseConnector):
    source  = "flipkart"
    country = "IN"

    INR_TO_USD = 1 / 84.0

    def fetch(self, query: str = "mobiles", limit: int = 20) -> list[dict]:
        log.info(f"[FlipkartConnector] Fetching query={query!r} country=IN")
        return self._mock_fetch(query, limit)

    def _mock_fetch(self, query: str, limit: int) -> list[dict]:
        import random, hashlib

        seed = hashlib.md5(f"flipkart:{query}".encode()).hexdigest()
        random.seed(seed)

        pool = [
            "Samsung Galaxy M", "Realme Narzo", "boAt Rockerz",
            "Redmi Note", "OnePlus Nord", "Mi Smart Band",
            "Noise ColorFit", "JBL Flip", "Fire-Boltt Ninja", "Fastrack Reflex"
        ]

        products = []
        for i, base_name in enumerate(pool[:limit]):
            price_inr   = random.randint(800, 80000)
            orig_inr    = int(price_inr * random.uniform(1.05, 1.5))
            price_usd   = round(price_inr * self.INR_TO_USD, 2)
            orig_usd    = round(orig_inr  * self.INR_TO_USD, 2)
            rating      = round(random.uniform(3.2, 4.9), 1)
            reviews     = random.randint(100, 50000)

            products.append({
                "id":           f"fk-{seed[:8]}-{i}",
                "product_name": f"{base_name} {random.randint(1,9)} ({query.title()})",
                "price":        price_usd,
                "original_price": orig_usd,
                "rating":       rating,
                "reviews":      reviews,
                "category":     query.title(),
                "image_url":    f"https://via.placeholder.com/200?text=Flipkart",
                "product_url":  f"https://www.flipkart.com/p/{seed[:10]}-{i}",
            })
        return products


# -------------------------------------------------------
# CONNECTOR REGISTRY
# Maps source name → connector class
# -------------------------------------------------------
CONNECTORS: dict[str, type[BaseConnector]] = {
    "fakestore": FakeStoreConnector,
    "amazon":    AmazonConnector,
    "flipkart":  FlipkartConnector,
}


def get_connector(source: str, country: str = "US") -> BaseConnector:
    """Factory — returns an instantiated connector."""
    cls = CONNECTORS.get(source.lower())
    if not cls:
        raise ValueError(f"Unknown connector source: {source!r}. Available: {list(CONNECTORS)}")
    instance = cls()
    instance.country = country.upper()[:2]
    return instance


# -------------------------------------------------------
# REAL AMAZON API (appended — does not modify mock above)
# Uses RapidAPI "Real-Time Amazon Data" endpoint.
# Falls back to _mock_fetch automatically on any error.
# Requires env: RAPIDAPI_KEY
# -------------------------------------------------------
class AmazonConnector(AmazonConnector):  # noqa: F811 — intentional override
    _RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"

    _COUNTRY_MAP = {
        "US": "US", "IN": "IN", "GB": "GB",
        "CA": "CA", "AU": "AU", "DE": "DE",
    }

    def fetch(self, query: str = "electronics", limit: int = 20) -> list[dict]:
        api_key = os.getenv("RAPIDAPI_KEY", "").strip()
        if not api_key:
            log.info("[AmazonConnector] No RAPIDAPI_KEY — using mock")
            return self._mock_fetch(query, limit)
        try:
            return self._real_fetch(query, limit, api_key)
        except Exception as e:
            log.warning(f"[AmazonConnector] Real API failed ({e}), falling back to mock")
            return self._mock_fetch(query, limit)

    def _real_fetch(self, query: str, limit: int, api_key: str) -> list[dict]:
        country = self._COUNTRY_MAP.get(self.country, "US")
        url = f"https://{self._RAPIDAPI_HOST}/search"
        headers = {
            "X-RapidAPI-Key":  api_key,
            "X-RapidAPI-Host": self._RAPIDAPI_HOST,
        }
        params = {
            "query":   query,
            "page":    "1",
            "country": country,
            "sort_by": "RELEVANCE",
            "product_condition": "ALL",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw_products = data.get("data", {}).get("products", [])[:limit]
        return [self._map_real(p) for p in raw_products if p.get("product_title")]

    @staticmethod
    def _map_real(p: dict) -> dict:
        def _price(v):
            if not v:
                return 0.0
            try:
                return float(str(v).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                return 0.0

        return {
            "id":             p.get("asin", ""),
            "product_name":   p.get("product_title", ""),
            "price":          _price(p.get("product_price")),
            "original_price": _price(p.get("product_original_price")) or _price(p.get("product_price")),
            "rating":         float(p.get("product_star_rating") or 0),
            "reviews":        int(p.get("product_num_ratings") or 0),
            "category":       p.get("product_category") or "General",
            "image_url":      p.get("product_photo", ""),
            "product_url":    p.get("product_url", ""),
        }


# -------------------------------------------------------
# REAL FLIPKART SCRAPING (appended — does not modify mock)
# Uses ScraperAPI to fetch Flipkart search page HTML,
# parses with BeautifulSoup. Falls back to mock on any error.
# Requires env: SCRAPERAPI_KEY
# -------------------------------------------------------
class FlipkartConnector(FlipkartConnector):  # noqa: F811 — intentional override

    INR_TO_USD = 1 / 84.0

    def fetch(self, query: str = "mobiles", limit: int = 20) -> list[dict]:
        api_key = os.getenv("SCRAPERAPI_KEY", "").strip()
        if not api_key:
            log.info("[FlipkartConnector] No SCRAPERAPI_KEY — using mock")
            return self._mock_fetch(query, limit)
        try:
            return self._real_fetch(query, limit, api_key)
        except Exception as e:
            log.warning(f"[FlipkartConnector] Real scrape failed ({e}), falling back to mock")
            return self._mock_fetch(query, limit)

    def _real_fetch(self, query: str, limit: int, api_key: str) -> list[dict]:
        from urllib.parse import quote_plus
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise RuntimeError("beautifulsoup4 not installed — pip install beautifulsoup4")

        target_url = f"https://www.flipkart.com/search?q={quote_plus(query)}&sort=relevance"
        scraper_url = "http://api.scraperapi.com/"
        params = {
            "api_key": api_key,
            "url":     target_url,
            "render":  "false",
        }
        resp = requests.get(scraper_url, params=params, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        products = []

        # Flipkart uses two common product card layouts — try both selectors
        cards = soup.select("div[data-id]") or soup.select("div._1AtVbE")
        for card in cards[:limit]:
            try:
                name_el  = card.select_one("div._4rR01T") or card.select_one("a.s1Q9rs") or card.select_one("div.KzDlHZ")
                price_el = card.select_one("div._30jeq3") or card.select_one("div.Nx9bqj")
                orig_el  = card.select_one("div._3I9_wc") or card.select_one("div.yRaY8j")
                rat_el   = card.select_one("div._3LWZlK")
                rev_el   = card.select_one("span._2_R_DZ") or card.select_one("span.Wphh3N")
                link_el  = card.select_one("a[href]")

                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue

                def _inr(el):
                    if not el:
                        return 0.0
                    txt = el.get_text(strip=True).replace("₹", "").replace(",", "")
                    try:
                        return float(txt) * FlipkartConnector.INR_TO_USD
                    except (ValueError, TypeError):
                        return 0.0

                price    = _inr(price_el)
                orig     = _inr(orig_el) or price
                rating   = float(rat_el.get_text(strip=True)) if rat_el else 0.0
                reviews  = 0
                if rev_el:
                    import re
                    m = re.search(r"[\d,]+", rev_el.get_text())
                    reviews = int(m.group().replace(",", "")) if m else 0

                href = link_el["href"] if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.flipkart.com" + href

                products.append({
                    "id":             card.get("data-id", ""),
                    "product_name":   name,
                    "price":          round(price, 2),
                    "original_price": round(orig, 2),
                    "rating":         rating,
                    "reviews":        reviews,
                    "category":       query.title(),
                    "image_url":      "",
                    "product_url":    href,
                })
            except Exception as ex:
                log.debug(f"[FlipkartConnector] Card parse error: {ex}")
                continue

        if not products:
            raise RuntimeError("Parsed 0 products — page structure may have changed")

        log.info(f"[FlipkartConnector] Real scrape: {len(products)} products")
        return products


# Update registry to point to overridden classes
CONNECTORS["amazon"]   = AmazonConnector
CONNECTORS["flipkart"] = FlipkartConnector
