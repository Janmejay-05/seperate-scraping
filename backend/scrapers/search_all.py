# backend/scrapers/search_all.py

"""
Aggregator that searches all platforms concurrently and returns combined,
comparable results.  Includes fuzzy-matching to group the same product
across different platforms so the user can see where it's cheapest.
"""

import asyncio
import re
import sys
from typing import List, Dict, Any

from fuzzywuzzy import fuzz

from backend.scrapers.blinkit_scraper import search_blinkit
from backend.scrapers.dmart_scraper import search_dmart
from backend.scrapers.jiomart_scraper import search_jiomart
from backend.scrapers.instamart_scraper import search_instamart


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

PLATFORM_LABELS = {
    "blinkit": "Blinkit",
    "dmart": "DMart",
    "jiomart": "JioMart",
    "instamart": "Instamart",
}


def normalize_product_name(name: str) -> str:
    """Remove quantity/unit tokens and lowercase for fuzzy matching."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(
        r'\d+(?:\.\d+)?\s*(?:kg|g|gm|gram|l|litre|liter|ml|pc|pcs|piece|pieces|pack|unit|units|drops|pellets)',
        '', n,
    )
    n = re.sub(r'[:\-–()/]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _harmonize(item: dict) -> dict:
    """
    Ensure every product dict has a consistent set of keys
    regardless of which scraper produced it.
    """
    # Map `source` → `platform` (display-friendly label)
    src = item.pop("source", None) or item.get("platform", "")
    item["platform"] = PLATFORM_LABELS.get(src.lower(), src) if src else item.get("platform", "Unknown")

    # Guarantee all expected keys exist
    item.setdefault("name", "")
    item.setdefault("price", None)
    item.setdefault("original_price", None)
    item.setdefault("discount", "")
    item.setdefault("quantity", None)
    item.setdefault("quantity_grams", None)
    item.setdefault("unit_price", None)
    item.setdefault("image_url", "")
    item.setdefault("link", "")
    item.setdefault("in_stock", True)

    # Compute unit_price if missing but we have price + weight
    if item["unit_price"] is None and item["price"] and item["quantity_grams"]:
        item["unit_price"] = round(item["price"] / item["quantity_grams"], 4)

    return item


def find_similar_products(results: List[dict], threshold: int = 65) -> List[List[dict]]:
    """
    Group similar products across platforms using fuzzy matching.
    Returns groups (including single-item groups).
    """
    if not results:
        return []

    for item in results:
        item["_norm"] = normalize_product_name(item.get("name", ""))

    groups: List[List[dict]] = []
    used = set()

    for i, item in enumerate(results):
        if i in used:
            continue

        group = [item]
        used.add(i)

        for j, other in enumerate(results):
            if j in used:
                continue
            # Only group items from DIFFERENT platforms
            if item["platform"] == other["platform"]:
                continue
            sim = fuzz.token_set_ratio(item["_norm"], other["_norm"])
            if sim >= threshold:
                group.append(other)
                used.add(j)

        groups.append(group)

    # Sort groups: multi-platform first, then by lowest price
    def group_sort_key(g):
        platforms = len({p["platform"] for p in g})
        best_price = min((p["price"] for p in g if p.get("price")), default=999999)
        return (-platforms, best_price)

    groups.sort(key=group_sort_key)
    return groups


def annotate_best_deals(groups: List[List[dict]]) -> List[dict]:
    """
    For each group, find the cheapest option and mark it.
    Returns flat list of best deals (one per group with 2+ platforms).
    """
    best_deals = []
    for gid, group in enumerate(groups):
        # Tag every product with its comparison_id
        for item in group:
            item["comparison_id"] = gid

        priced = [p for p in group if p.get("price")]
        if not priced:
            continue

        # Best by unit_price first, then by absolute price
        with_up = [p for p in priced if p.get("unit_price")]
        if with_up:
            best = min(with_up, key=lambda x: x["unit_price"])
        else:
            best = min(priced, key=lambda x: x["price"])

        best["is_best_deal"] = True

        # Calculate savings vs most expensive in group
        if len(priced) > 1:
            most_expensive = max(priced, key=lambda x: x["price"])
            if most_expensive["price"] > best["price"]:
                savings = most_expensive["price"] - best["price"]
                pct = round(savings / most_expensive["price"] * 100)
                best["savings"] = f"₹{savings:.0f} cheaper ({pct}% less)"

        if len(group) > 1:
            best_deals.append(best)

    return best_deals


# ─────────────────────────────────────────────────
# Main aggregator
# ─────────────────────────────────────────────────

async def search_all(
    query: str,
    pincode: str = "380015",
    lat: float = 23.0225,
    lng: float = 72.5714,
    max_results: int = 40,
    headful: bool = False,
) -> Dict[str, Any]:
    """Search all platforms concurrently and return combined results."""

    print(f"\n========== SEARCH ALL PLATFORMS: {query} ==========\n")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    all_results: List[dict] = []
    by_platform: Dict[str, List[dict]] = {}
    errors: List[dict] = []

    # Run all scrapers concurrently
    tasks = [
        search_blinkit(query=query, pincode=pincode, max_results=max_results, headful=headful),
        search_dmart(query=query, pincode=pincode, max_results=max_results, headful=headful),
        search_jiomart(query=query, pincode=pincode, max_results=max_results, headful=headful),
        search_instamart(query=query, lat=lat, lng=lng, max_results=max_results, headful=headful),
    ]

    platform_keys = ["Blinkit", "DMart", "JioMart", "Instamart"]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results_list):
        pname = platform_keys[i]
        if isinstance(result, Exception):
            print(f"[AGG] {pname} FAILED: {result}")
            import traceback as tb
            tb.print_exception(type(result), result, result.__traceback__)
            errors.append({"platform": pname, "error": str(result)})
            by_platform[pname] = []
        else:
            items = result if isinstance(result, list) else []
            # Harmonize every item
            items = [_harmonize(item) for item in items]
            all_results.extend(items)
            by_platform[pname] = items
            print(f"[AGG] {pname}: {len(items)} items")

    # Build comparison groups
    comparison_groups = find_similar_products(all_results)
    best_deals = annotate_best_deals(comparison_groups)

    # Clean up internal keys before sending to frontend
    for item in all_results:
        item.pop("_norm", None)
        item.pop("normalized_name", None)

    # Sort all results: best value first
    def sort_key(item):
        up = item.get("unit_price")
        p = item.get("price")
        if up:
            return (0, up)
        elif p:
            return (1, p)
        return (2, 999999)

    all_results_sorted = sorted(all_results, key=sort_key)

    # Serialize comparison groups for frontend (list of lists)
    comparisons_serialized = []
    for group in comparison_groups:
        cleaned = []
        for item in group:
            c = dict(item)
            c.pop("_norm", None)
            c.pop("normalized_name", None)
            cleaned.append(c)
        if len(cleaned) > 1:  # only multi-platform groups
            comparisons_serialized.append(cleaned)

    print(f"\n[AGG] Total: {len(all_results_sorted)} results, "
          f"{len(comparisons_serialized)} comparison groups, "
          f"{len(best_deals)} best deals\n")

    return {
        "query": query,
        "all_results": all_results_sorted,
        "by_platform": by_platform,
        "comparisons": comparisons_serialized,
        "best_deals": best_deals,
        "errors": errors,
    }
