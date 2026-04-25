"""
Blinkit scraper — uses Playwright to navigate blinkit.com,
set location via pincode, search for a product, and extract structured data.

Key findings from debugging (Feb 2026):
  - Search URL: /s/?q={query}
  - Location: enter pincode in search input → select suggestion
  - Product cards: div[role='button'][id] (id = product ID, skip id="product_container")
  - Each card innerText follows:
      {discount}% OFF       ← optional
      {delivery} MINS       ← delivery time
      {product name}
      {quantity}            ← e.g. "1 kg", "500 g"
      ₹{sale_price}
      ₹{original_price}    ← optional, strikethrough MRP
      ADD
  - Images: cdn.grofers.com CDN (first img = product, second = ETA icon)
  - No anchor links — cards are div[role='button']
"""

import asyncio
import os
import re
import random
from typing import List, Dict, Any
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
delete navigator.__proto__.webdriver;
"""


def extract_quantity(text: str):
    """Extract quantity and unit from product name or quantity line."""
    if not text:
        return None, None, None

    text_lower = text.lower()

    patterns = [
        (r'(\d+(?:\.\d+)?)\s*kg', 'kg', 1000),
        (r'(\d+(?:\.\d+)?)\s*g(?:m|ram)?(?:\s|$|,)', 'g', 1),
        (r'(\d+(?:\.\d+)?)\s*l(?:itre|iter)?(?:\s|$|,)', 'l', 1000),
        (r'(\d+(?:\.\d+)?)\s*ml', 'ml', 1),
        (r'(\d+)\s*(?:pc|pcs|piece|pieces|pack)', 'pcs', None),
    ]

    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1))
            grams = value * multiplier if multiplier else None
            return value, unit, grams

    return None, None, None


async def search_blinkit(
    query: str,
    pincode: str = "380015",
    max_results: int = 20,
    headful: bool = False,
    timeout: int = 60000,
) -> List[Dict[str, Any]]:
    """
    Search Blinkit for products matching *query*.

    Returns a list of dicts with keys:
        name, price, original_price, discount, quantity, image_url,
        source, in_stock
    """
    print(f"[BLINKIT] Searching: {query}, pincode={pincode}, headful={headful}")

    results: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headful,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            bypass_csp=True,
        )

        page = await context.new_page()
        await page.add_init_script(STEALTH_JS)

        try:
            # ── 1. Navigate to homepage & set location ───────────────
            print("[BLINKIT] Opening homepage for location setup...")
            await page.goto(
                "https://blinkit.com/",
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            await page.wait_for_timeout(random.randint(3000, 5000))

            # Handle location
            await _set_location(page, pincode)

            # ── 2. Navigate to search results ────────────────────────
            search_url = f"https://blinkit.com/s/?q={quote_plus(query)}"
            print(f"[BLINKIT] Opening: {search_url}")
            await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            await page.wait_for_timeout(random.randint(3000, 5000))

            # ── 3. Wait for products ─────────────────────────────────
            try:
                await page.wait_for_selector(
                    "div[role='button'][id]:not([id='product_container'])",
                    timeout=20000,
                )
            except Exception:
                print("[BLINKIT] Timeout waiting for products, checking anyway...")

            # ── 4. Scroll to load more products ─────────────────────
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(random.randint(400, 700))
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # ── 5. Extract via JS ────────────────────────────────────
            raw_products = await page.evaluate("""() => {
                const cards = document.querySelectorAll("div[role='button'][id]");
                const results = [];

                for (const card of cards) {
                    // Skip the "Showing results for" header
                    if (card.id === 'product_container' || card.id === '') continue;

                    const text = card.innerText;
                    if (!text || text.length < 10) continue;

                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                    // Get the product image (first cdn.grofers.com image)
                    let imageUrl = '';
                    const imgs = card.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src || img.getAttribute('src') || '';
                        // Product images are on grofers CDN, skip ETA icons
                        if (src.includes('cdn.grofers.com') && src.includes('product')) {
                            imageUrl = src;
                            break;
                        }
                    }
                    // Fallback: take first grofers image
                    if (!imageUrl) {
                        for (const img of imgs) {
                            const src = img.src || img.getAttribute('src') || '';
                            if (src.includes('cdn.grofers.com') && !src.includes('eta-icon')) {
                                imageUrl = src;
                                break;
                            }
                        }
                    }

                    results.push({
                        id: card.id,
                        lines,
                        imageUrl,
                    });
                }
                return results;
            }""")

            print(f"[BLINKIT] Found {len(raw_products)} product cards")

            # ── 6. Parse structured fields ───────────────────────────
            for card in raw_products:
                product = _parse_card_lines(card["lines"], card["id"], card["imageUrl"])
                if product:
                    results.append(product)
                    if len(results) >= max_results:
                        break

        except Exception as exc:
            print(f"[BLINKIT] Error: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

    print(f"[BLINKIT] Returning {len(results)} results")
    return results


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _set_location(page, pincode: str) -> None:
    """Enter pincode in the Blinkit location input and select a suggestion."""
    try:
        # Try to find the location input directly (modal may already be open)
        location_input = await page.query_selector(
            "input[name='select-locality'], "
            "input[placeholder*='search' i], "
            "input[class*='search']"
        )

        if not location_input:
            # Click the location header to open the picker
            loc_header = await page.query_selector(
                "div[class*='Location'], "
                "div[class*='Header'] div[class*='arrow']"
            )
            if loc_header:
                await loc_header.click()
                await page.wait_for_timeout(random.randint(1000, 2000))
                location_input = await page.query_selector(
                    "input[name='select-locality'], "
                    "input[placeholder*='search' i]"
                )

        if location_input:
            print(f"[BLINKIT] Entering pincode: {pincode}")
            await location_input.fill(pincode)
            await page.wait_for_timeout(2000)

            # Click first suggestion
            try:
                suggestion = await page.wait_for_selector(
                    "div[class*='LocationSearchList'] div, "
                    "div[class*='pac-item'], "
                    "div[role='button']",
                    timeout=5000,
                )
                if suggestion:
                    print("[BLINKIT] Selecting location suggestion...")
                    await suggestion.click()
                    await page.wait_for_timeout(random.randint(2000, 4000))
            except Exception:
                print("[BLINKIT] No location suggestions found")
        else:
            print("[BLINKIT] No location input found (may already be set)")

    except Exception as e:
        print(f"[BLINKIT] Location handling error: {e}")


def _parse_card_lines(
    lines: list,
    product_id: str,
    image_url: str,
) -> dict | None:
    """
    Parse Blinkit product card lines.

    Expected order:
        {discount}% OFF     ← optional
        {delivery} MINS     ← delivery time (skip)
        {product name}
        {quantity}           ← e.g. "1 kg"
        ₹{sale_price}
        ₹{original_price}   ← optional strikethrough MRP
        ADD
    """
    if len(lines) < 3:
        return None

    idx = 0
    discount_str = ""

    # Optional: "{N}% OFF"
    if idx < len(lines) and re.match(r'\d+%\s*OFF', lines[idx], re.I):
        discount_str = lines[idx]
        idx += 1

    # Optional: delivery time "{N} MINS"
    if idx < len(lines) and re.match(r'\d+\s*MINS?', lines[idx], re.I):
        idx += 1

    # Product name
    name = lines[idx] if idx < len(lines) else ""
    idx += 1
    if not name or name == "ADD":
        return None

    # Quantity line
    quantity = ""
    if idx < len(lines) and not lines[idx].startswith("₹"):
        quantity = lines[idx]
        idx += 1

    # Sale price: ₹{price}
    sale_price = None
    if idx < len(lines):
        sale_price = _extract_price(lines[idx])
        idx += 1

    # Original price (optional): ₹{mrp}
    original_price = None
    if idx < len(lines) and lines[idx].startswith("₹"):
        original_price = _extract_price(lines[idx])
        idx += 1

    if not name or sale_price is None:
        return None

    # Extract quantity details
    qty_val, qty_unit, qty_grams = extract_quantity(quantity or name)

    # Unit price
    unit_price = None
    if sale_price and qty_grams:
        unit_price = round(sale_price / qty_grams, 4)

    return {
        "name": name,
        "price": sale_price,
        "original_price": original_price,
        "discount": discount_str,
        "quantity": f"{qty_val} {qty_unit}" if qty_val else quantity,
        "quantity_grams": qty_grams,
        "unit_price": unit_price,
        "image_url": image_url,
        "source": "blinkit",
        "in_stock": True,  # If visible on search results, it's in stock
        "link": f"https://blinkit.com/prn/{name.lower().replace(' ', '-')}/prid/{product_id}",
    }


def _extract_price(text: str) -> float | None:
    """Pull the first decimal number out of a string like '₹54'."""
    if not text:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None
