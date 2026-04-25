# backend/filters/filter_engine.py

import re

def clean_text(t):
    if not t:
        return ""
    return t.lower().strip()

def matches_item(r, query_item, modifiers):
    name = clean_text(r.get("name") or "")
    query_item = clean_text(query_item)

    # if name doesn't contain pizza, check meta/cuisines/etc.
    if query_item not in name:
        tags = clean_text(r.get("meta") or "")
        if query_item not in tags:
            return False

    # Check modifiers
    for m in modifiers:
        if m not in name and m not in tags:
            return False

    return True


def is_under_budget(price_value, budget):
    if budget is None:
        return True
    if price_value is None:
        return True    # <-- allow missing prices
    return price_value <= budget

def filter_by_rating(rating_str, min_rating=3.5):
    if not rating_str:
        return True   # <-- allow missing ratings
    try:
        return float(rating_str) >= min_rating
    except:
        return True

def filter_engine(
    results: list,
    item: str,
    modifiers: list,
    budget: int,
    is_veg: bool,
    min_rating: float = 3.5
):
    filtered = []

    for r in results:

        # item filter
        if item and not matches_item(r, item, modifiers):
            continue


        # budget
        if not is_under_budget(r.get("price_value"), budget):
            continue

        # rating
        if not filter_by_rating(r.get("rating"), min_rating):
            continue

        # veg filter
        nm = clean_text(r.get("name"))
        if is_veg is True and "non veg" in nm:
            continue
        if is_veg is False and "veg" in nm:
            continue

        filtered.append(r)

    return filtered
