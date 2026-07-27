"""
Alternative Data Service — Digital Due Diligence

Provides two async data sources for any sourced target:
  1. **Tech Stack** — BuiltWith API (or curated mock when key absent).
  2. **Google Trends** — pytrends / scraping fallback for 12-month search interest.

Designed to *never crash*: every external call is wrapped in try/except
and returns a typed dict with a `source` flag ("live" | "mock" | "error").
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from api.config import get_settings


# ============================================================
#  1.  Tech Stack — BuiltWith API
# ============================================================

# Curated mock stacks used for graceful degradation
_MOCK_STACKS: dict[str, list[dict[str, str]]] = {
    "default": [
        {"name": "React", "category": "JavaScript Framework"},
        {"name": "Node.js", "category": "Web Server"},
        {"name": "Cloudflare", "category": "CDN"},
        {"name": "Google Analytics", "category": "Analytics"},
        {"name": "Stripe", "category": "Payment"},
        {"name": "AWS", "category": "Hosting"},
        {"name": "HubSpot", "category": "Marketing Automation"},
        {"name": "Intercom", "category": "Live Chat"},
    ],
    "saas": [
        {"name": "React", "category": "JavaScript Framework"},
        {"name": "TypeScript", "category": "Programming Language"},
        {"name": "Stripe", "category": "Payment"},
        {"name": "AWS", "category": "Hosting"},
        {"name": "Segment", "category": "Analytics"},
        {"name": "Auth0", "category": "Authentication"},
        {"name": "Datadog", "category": "Monitoring"},
        {"name": "Mixpanel", "category": "Product Analytics"},
        {"name": "Intercom", "category": "Live Chat"},
        {"name": "Cloudflare", "category": "CDN"},
    ],
    "ecommerce": [
        {"name": "Shopify", "category": "E-commerce Platform"},
        {"name": "Stripe", "category": "Payment"},
        {"name": "Google Analytics", "category": "Analytics"},
        {"name": "Klaviyo", "category": "Email Marketing"},
        {"name": "Cloudflare", "category": "CDN"},
        {"name": "Zendesk", "category": "Support"},
        {"name": "Facebook Pixel", "category": "Advertising"},
        {"name": "Google Tag Manager", "category": "Tag Management"},
    ],
}

# Map tech names to a category color hint (consumed by the frontend)
_TECH_CATEGORIES: dict[str, str] = {
    "JavaScript Framework": "cyan",
    "Programming Language": "violet",
    "Payment": "emerald",
    "Hosting": "amber",
    "CDN": "blue",
    "Analytics": "rose",
    "Product Analytics": "rose",
    "Marketing Automation": "orange",
    "E-commerce Platform": "emerald",
    "Email Marketing": "orange",
    "Live Chat": "violet",
    "Support": "violet",
    "Advertising": "blue",
    "Tag Management": "slate",
    "Authentication": "amber",
    "Monitoring": "cyan",
    "Web Server": "amber",
}


async def _fetch_builtwith(domain: str) -> dict[str, Any]:
    """Call the BuiltWith Free/Pro API and normalise the response."""
    settings = get_settings()
    key = settings.builtwith_api_key

    if not key:
        logger.info("[ALT-DATA] No BUILTWITH_API_KEY — using mock tech stack for {}", domain)
        return _mock_tech_stack(domain)

    url = f"https://api.builtwith.com/free1/api.json?KEY={key}&LOOKUP={domain}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        # BuiltWith Free API returns {"Results": [{"Result": {"Paths": [{"Technologies": [...]}]}}]}
        techs: list[dict[str, str]] = []
        results = data.get("Results", [])
        if results:
            paths = results[0].get("Result", {}).get("Paths", [])
            for path in paths:
                for tech in path.get("Technologies", []):
                    name = tech.get("Name", "")
                    cat = tech.get("Tag", tech.get("Categories", ["Other"])[0] if tech.get("Categories") else "Other")
                    if name and not any(t["name"] == name for t in techs):
                        techs.append({
                            "name": name,
                            "category": cat,
                            "color": _TECH_CATEGORIES.get(cat, "slate"),
                        })

        if not techs:
            logger.warning("[ALT-DATA] BuiltWith returned empty for {} — fallback to mock", domain)
            return _mock_tech_stack(domain)

        logger.info("[ALT-DATA] BuiltWith returned {} techs for {}", len(techs), domain)
        return {
            "technologies": techs[:20],  # cap at 20
            "source": "builtwith",
            "domain": domain,
        }

    except Exception as exc:
        logger.warning("[ALT-DATA] BuiltWith API error for {} : {} — fallback to mock", domain, exc)
        return _mock_tech_stack(domain)


def _mock_tech_stack(domain: str) -> dict[str, Any]:
    """Return a realistic mock tech stack, varying by domain keywords."""
    lower = domain.lower()
    if any(kw in lower for kw in ("shop", "store", "boutique", "ecommerce", "commerce")):
        base = _MOCK_STACKS["ecommerce"]
    elif any(kw in lower for kw in ("app", "saas", "cloud", "io", "platform", "tech")):
        base = _MOCK_STACKS["saas"]
    else:
        base = _MOCK_STACKS["default"]

    # Randomise slightly so each domain looks different
    rng = random.Random(hash(domain))
    stack = rng.sample(base, min(len(base), rng.randint(5, len(base))))
    for t in stack:
        t["color"] = _TECH_CATEGORIES.get(t["category"], "slate")

    return {
        "technologies": stack,
        "source": "mock",
        "domain": domain,
    }


# ============================================================
#  2.  Google Trends — 12-month search interest
# ============================================================

async def _fetch_google_trends(company_name: str) -> dict[str, Any]:
    """Fetch 12-month Google search interest via pytrends.

    pytrends is synchronous (uses requests internally), so we run it
    in a thread executor to avoid blocking the event loop.
    Falls back to synthetic data if pytrends is unavailable or fails.
    """
    try:
        from pytrends.request import TrendReq  # lazy import — optional dep

        def _blocking_trends():
            pt = TrendReq(hl="fr-FR", tz=60, timeout=(10, 25))
            pt.build_payload([company_name], cat=0, timeframe="today 12-m", geo="FR")
            df = pt.interest_over_time()
            if df.empty:
                return None

            rows = []
            for ts, row in df.iterrows():
                rows.append({
                    "date": ts.strftime("%Y-%m-%d"),
                    "value": int(row[company_name]),
                })
            return rows

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _blocking_trends)

        if data:
            logger.info("[ALT-DATA] Google Trends OK for '{}' — {} points", company_name, len(data))
            return {
                "keyword": company_name,
                "points": data,
                "source": "google_trends",
            }
        else:
            logger.info("[ALT-DATA] Google Trends returned empty for '{}' — using mock", company_name)
            return _mock_trends(company_name)

    except ImportError:
        logger.info("[ALT-DATA] pytrends not installed — using mock trends for '{}'", company_name)
        return _mock_trends(company_name)
    except Exception as exc:
        logger.warning("[ALT-DATA] Google Trends error for '{}' : {} — using mock", company_name, exc)
        return _mock_trends(company_name)


def _mock_trends(company_name: str) -> dict[str, Any]:
    """Generate realistic-looking synthetic Google Trends data."""
    rng = random.Random(hash(company_name))
    today = datetime.now()
    base = rng.randint(25, 65)
    points = []

    for i in range(52):  # 52 weeks
        date = today - timedelta(weeks=52 - i)
        # Upward drift + seasonal noise
        trend = base + (i * rng.uniform(0.1, 0.6))
        noise = rng.gauss(0, 5)
        val = max(0, min(100, int(trend + noise)))
        points.append({
            "date": date.strftime("%Y-%m-%d"),
            "value": val,
        })

    return {
        "keyword": company_name,
        "points": points,
        "source": "mock",
    }


# ============================================================
#  3.  Public Orchestrator
# ============================================================

async def get_digital_dd(domain: str, company_name: str) -> dict[str, Any]:
    """Run all Digital DD modules concurrently and return a unified report.

    Returns:
        {
            "domain": "...",
            "company_name": "...",
            "tech_stack": { "technologies": [...], "source": "builtwith"|"mock" },
            "search_trends": { "keyword": "...", "points": [...], "source": "google_trends"|"mock" },
            "generated_at": "ISO-8601"
        }
    """
    # Clean domain (strip protocol / path)
    parsed = urlparse(domain if domain.startswith("http") else f"https://{domain}")
    clean_domain = parsed.netloc or parsed.path.split("/")[0]
    clean_domain = clean_domain.removeprefix("www.")

    logger.info("[ALT-DATA] ▶ Digital DD for {} ({})", company_name, clean_domain)

    tech_task = _fetch_builtwith(clean_domain)
    trends_task = _fetch_google_trends(company_name)

    tech_result, trends_result = await asyncio.gather(tech_task, trends_task)

    return {
        "domain": clean_domain,
        "company_name": company_name,
        "tech_stack": tech_result,
        "search_trends": trends_result,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
