"""
JioMart scraper — uses Playwright to navigate jiomart.com,
search for a product, and extract structured data.

Key findings from debugging (Feb 2026):
  - Search URL: /search/?q={query}
  - Product cards: li.ais-InfiniteHits-item (also a.plp-card-wrapper inside)
  - Sponsored items: li[type="sponsored"] — skip them
  - Each card innerText follows:
      [Optional: "Sponsored"]
      {product name}
      ₹{sale_price} ₹{original_price}    ← both on same line, space-separated
      OR  ₹{sale_price}(₹ xx.xx/1 kg) ₹{mrp}   ← unit price embedded
      {discount}% OFF
      [Optional: promotional text "Flat Rs.50 Off..."]
      Add
  - Images: jiomart.com/images/product/... (first img is product)
  - Links: a.plp-card-wrapper href = full product URL
"""

import asyncio
import random
import re
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
        (r'(\d+(?:\.\d+)?)\s*g(?:m|ram)?(?:\s|$|,|\))', 'g', 1),
        (r'(\d+(?:\.\d+)?)\s*l(?:itre|iter)?(?:\s|$|,|\))', 'l', 1000),
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


async def search_jiomart(
    query: str,
    pincode: str = "380015",
    max_results: int = 40,
    headful: bool = False,
    timeout: int = 60000,
) -> List[Dict[str, Any]]:
    """
    Search JioMart for products matching *query*.

    Returns a list of dicts with keys:
        name, price, original_price, discount, quantity, image_url,
        source, in_stock, link
    """
    print(f"[JIOMART] Searching: {query}, pincode={pincode}, headful={headful}")

    results: List[Dict[str, Any]] = []
    search_url = f"https://www.jiomart.com/search/?q={quote_plus(query)}"
    print(f"[JIOMART] Opening: {search_url}")

    async with async_playwright() as p:
        # JioMart aggressively blocks headless browsers — always launch
        # headful.  When the caller didn't ask for a visible window we
        # move it off-screen so it stays invisible.
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]
        if not headful:
            launch_args.append("--window-position=-2400,-2400")

        browser = await p.chromium.launch(
            headless=False,          # always headful — headless gets blocked
            args=launch_args,
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
            # ── 1. Navigate to search page ──────────────────
            await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(random.randint(4000, 6000))

            # Dismiss modals
            for sel in [
                "button:has-text('OK')",
                "button:has-text('Not Now')",
                "button:has-text('Allow')",
                "[aria-label='Close']",
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

            # ── 2. Wait for products ────────────────────────
            try:
                await page.wait_for_selector(
                    "li.ais-InfiniteHits-item",
                    timeout=30000,
                )
            except Exception:
                print("[JIOMART] Timeout waiting for products, checking anyway...")

            await page.wait_for_timeout(random.randint(2000, 4000))

            # ── 3. Scroll to load more products ─────────────
            for _ in range(8):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(random.randint(400, 700))
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # ── 4. Extract via JS ───────────────────────────
            raw_products = await page.evaluate("""() => {
                const cards = document.querySelectorAll('li.ais-InfiniteHits-item');
                const results = [];

                for (const card of cards) {
                    // Skip sponsored items
                    const cardType = card.getAttribute('type');
                    if (cardType && cardType.toLowerCase() === 'sponsored') continue;

                    const text = card.innerText;
                    if (!text || text.length < 10) continue;

                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                    // Get product image (first non-icon image)
                    let imageUrl = '';
                    const imgs = card.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src || '';
                        if (src.includes('/images/product/')) {
                            imageUrl = src;
                            break;
                        }
                    }

                    // Get product link
                    let link = '';
                    const anchor = card.querySelector('a.plp-card-wrapper');
                    if (anchor) {
                        link = anchor.href || anchor.getAttribute('href') || '';
                    }

                    results.push({ lines, imageUrl, link });
                }
                return results;
            }""")

            print(f"[JIOMART] Found {len(raw_products)} product cards (non-sponsored)")

            # ── 5. Parse structured fields ──────────────────
            for card in raw_products:
                product = _parse_card_lines(card["lines"], card["imageUrl"], card["link"])
                if product:
                    results.append(product)
                    if len(results) >= max_results:
                        break

        except Exception as exc:
            print(f"[JIOMART] Error: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

    print(f"[JIOMART] Returning {len(results)} results")
    return results


def _parse_card_lines(lines: list, image_url: str, link: str) -> dict | None:
    """
    Parse JioMart product card lines.

    Expected order:
        [Optional: "Sponsored"]   ← already filtered out
        {product name}
        ₹{sale_price} ₹{mrp}     OR  ₹{sale}(₹ xx/1 kg) ₹{mrp}
        {N}% OFF                  ← optional
        [promo text]              ← optional
        Add
    """
    if len(lines) < 2:
        return None

    idx = 0

    # Skip "Sponsored" if somehow still present
    if lines[idx].lower() == "sponsored":
        idx += 1

    # Product name
    name = lines[idx] if idx < len(lines) else ""
    idx += 1
    if not name or name == "Add":
        return None

    # Price line: "₹299.00 ₹360.00" or "₹549.00(₹ 54.90/1 kg) ₹700.00"
    sale_price = None
    original_price = None

    if idx < len(lines):
        price_line = lines[idx]
        # Extract all ₹ amounts from the line
        prices = re.findall(r'₹\s*([\d,]+(?:\.\d+)?)', price_line)
        if prices:
            sale_price = float(prices[0].replace(",", ""))
            if len(prices) >= 2:
                # Second price is the MRP (could be index 1 or last)
                # If there's a unit price in between, MRP is the last one
                original_price = float(prices[-1].replace(",", ""))
                # Sometimes the second price is less — swap if needed
                if original_price < sale_price:
                    sale_price, original_price = original_price, sale_price
            idx += 1

    # Discount line: "16% OFF"
    discount_str = ""
    if idx < len(lines) and re.match(r'\d+%\s*OFF', lines[idx], re.I):
        discount_str = lines[idx]
        idx += 1

    if not name or sale_price is None:
        return None

    # Extract quantity from name
    qty_val, qty_unit, qty_grams = extract_quantity(name)

    # Unit price
    unit_price = None
    if sale_price and qty_grams:
        unit_price = round(sale_price / qty_grams, 4)

    return {
        "name": name,
        "price": sale_price,
        "original_price": original_price,
        "discount": discount_str,
        "quantity": f"{qty_val} {qty_unit}" if qty_val else None,
        "quantity_grams": qty_grams,
        "unit_price": unit_price,
        "image_url": image_url,
        "source": "jiomart",
        "in_stock": True,
        "link": link,
    }
