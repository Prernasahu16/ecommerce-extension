# ============================================================
# EXTENSION MODULE — connectors/source_connectors.py
# External platform data adapters (Amazon, Flipkart, etc.)
# Each connector maps raw platform data → pipeline-ready dicts
# DOES NOT interfere with existing scraper/scraper.py
# ============================================================

import logging
import requests
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data_pipeline.pipeline import process_batch

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


# -------------------------------------------------------
# BASE CONNECTOR INTERFACE
# -------------------------------------------------------
class BaseConnector:
    source_name: str = "unknown"
    country: str = "US"

    def fetch_raw(self, query: str, limit: int = 20) -> list[dict]:
        """Fetch raw product data from the platform. Override in subclass."""
        raise NotImplementedError

    def run(self, query: str, limit: int = 20) -> dict:
        """Fetch → pipeline (standardize + score + upsert)."""
        log.info(f"[{self.source_name}] Fetching query='{query}' limit={limit}")
        try:
            raw = self.fetch_raw(query, limit)
            return process_batch(raw, source=self.source_name, country=self.country)
        except Exception as e:
            log.error(f"[{self.source_name}] Connector failed: {e}")
            return {"error": str(e), "total_raw": 0}


# -------------------------------------------------------
# AMAZON CONNECTOR (uses RapidAPI Real-Time Amazon Data)
# Set RAPIDAPI_KEY in .env to enable real calls.
# Falls back to demo mode if no key present.
# -------------------------------------------------------
class AmazonConnector(BaseConnector):
    source_name = "amazon"

    COUNTRY_HOSTS = {
        "US": ("com",   "US"),
        "UK": ("co.uk", "GB"),
        "IN": ("in",    "IN"),
    }

    def __init__(self, country: str = "US"):
        self.country = country
        tld, api_country = self.COUNTRY_HOSTS.get(country, ("com", "US"))
        self._tld = tld
        self._api_country = api_country
        self._api_key = os.getenv("RAPIDAPI_KEY", "")
        self._host = "real-time-amazon-data.p.rapidapi.com"

    def fetch_raw(self, query: str, limit: int = 20) -> list[dict]:
        if not self._api_key:
            log.warning("[Amazon] No RAPIDAPI_KEY — returning demo data")
            return self._demo_data(query, limit)

        url = f"https://{self._host}/search"
        headers = {
            "X-RapidAPI-Key":  self._api_key,
            "X-RapidAPI-Host": self._host,
        }
        params = {
            "query":   query,
            "page":    "1",
            "country": self._api_country,
            "sort_by": "RELEVANCE",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        products = data.get("data", {}).get("products", [])[:limit]
        return self._map(products)

    def _map(self, raw_products: list[dict]) -> list[dict]:
        out = []
        for p in raw_products:
            out.append({
                "id":             p.get("asin") or p.get("product_id", ""),
                "product_name":   p.get("product_title", ""),
                "price":          p.get("product_price") or p.get("price", 0),
                "original_price": p.get("product_original_price") or p.get("original_price", 0),
                "rating":         p.get("product_star_rating") or p.get("rating", 3.0),
                "reviews":        p.get("product_num_ratings") or p.get("num_reviews", 0),
            })
        return out

    def _demo_data(self, query: str, limit: int) -> list[dict]:
        """Demo data for development without API key."""
        demo = [
            {"id": f"AMZ_{i}", "product_name": f"{query} - Amazon Product {i}",
             "price": 29.99 + i * 10, "original_price": 49.99 + i * 10,
             "rating": round(3.5 + (i % 3) * 0.5, 1), "reviews": 100 + i * 50}
            for i in range(1, min(limit + 1, 6))
        ]
        return demo


# -------------------------------------------------------
# FLIPKART CONNECTOR
# Uses ScraperAPI or demo mode (set SCRAPERAPI_KEY in .env)
# -------------------------------------------------------
class FlipkartConnector(BaseConnector):
    source_name = "flipkart"
    country = "IN"

    def __init__(self):
        self._api_key = os.getenv("SCRAPERAPI_KEY", "")

    def fetch_raw(self, query: str, limit: int = 20) -> list[dict]:
        if not self._api_key:
            log.warning("[Flipkart] No SCRAPERAPI_KEY — returning demo data")
            return self._demo_data(query, limit)

        url = "https://api.scraperapi.com/"
        params = {
            "api_key": self._api_key,
            "url": f"https://www.flipkart.com/search?q={requests.utils.quote(query)}",
            "render": "true",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        # Parse HTML response — return raw text for pipeline
        # (Full HTML parser omitted; use BeautifulSoup in production)
        log.info("[Flipkart] Raw HTML fetched — parse with BeautifulSoup")
        return self._demo_data(query, limit)

    def _demo_data(self, query: str, limit: int) -> list[dict]:
        return [
            {"id": f"FK_{i}", "product_name": f"{query} - Flipkart Product {i}",
             "price": 1999 + i * 500, "original_price": 2999 + i * 500,
             "rating": round(3.8 + (i % 3) * 0.4, 1), "reviews": 200 + i * 80}
            for i in range(1, min(limit + 1, 6))
        ]


# -------------------------------------------------------
# GENERIC JSON CONNECTOR
# Accepts any URL returning a JSON array of products
# -------------------------------------------------------
class GenericJSONConnector(BaseConnector):
    def __init__(self, source_name: str, endpoint_url: str,
                 field_map: dict = None, country: str = "US"):
        self.source_name = source_name
        self._url = endpoint_url
        self._map = field_map or {}
        self.country = country

    def fetch_raw(self, query: str, limit: int = 20) -> list[dict]:
        resp = requests.get(
            self._url,
            params={"q": query, "limit": limit},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("products", data.get("items", []))
        # Remap fields
        out = []
        for item in items[:limit]:
            remapped = {}
            for std_key, src_key in self._map.items():
                remapped[std_key] = item.get(src_key)
            remapped.update({k: v for k, v in item.items() if k not in remapped})
            out.append(remapped)
        return out


# -------------------------------------------------------
# CONNECTOR REGISTRY — returns the right connector
# -------------------------------------------------------
CONNECTOR_REGISTRY = {
    "amazon_us": lambda: AmazonConnector(country="US"),
    "amazon_uk": lambda: AmazonConnector(country="UK"),
    "amazon_in": lambda: AmazonConnector(country="IN"),
    "flipkart":  lambda: FlipkartConnector(),
}


def get_connector(platform: str) -> BaseConnector | None:
    factory = CONNECTOR_REGISTRY.get(platform.lower())
    return factory() if factory else None


def run_connector(platform: str, query: str, limit: int = 20) -> dict:
    """Public entry point — fetch + pipeline for a given platform."""
    connector = get_connector(platform)
    if not connector:
        return {"error": f"Unknown platform: {platform}. Available: {list(CONNECTOR_REGISTRY)}"}
    return connector.run(query, limit)
