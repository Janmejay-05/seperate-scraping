"""
DMart Ready scraper  —  uses Playwright to navigate dmart.in,
set location via pincode, search for a product, and extract structured data.

Key findings from debugging (Feb 2026):
  - Search URL: /search?searchTerm={query}  (old /searchResult?searchText= gives 404)
  - Location modal: pincode input → select result → click "CONFIRM LOCATION"
  - Product cards are MUI Grid items (.MuiGrid-root.MuiGrid-item) with ₹ + "ADD TO CART"
  - Each card's innerText follows a fixed pattern:
      [Out Of Stock]
      Name
      MRP
      ₹ {mrp}
      DMart
      ₹ {sale}
      (Inclusive of all taxes)
      ₹ {discount}
      OFF
      {quantity}
      [(per-unit price)]
      ADD TO CART
  - Images on cdn.dmart.in via background-image or <img> src
  - Product title available as `title` attribute on the image div
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
delete navigator.__proto__.webdriver;
"""


async def search_dmart(
    query: str,
    pincode: str = "380015",
    max_results: int = 20,
    timeout: int = 60000,
    headful: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search DMart Ready for products matching *query*.

    Returns a list of dicts with keys:
        name, price, original_price, discount, quantity, image_url,
        source, in_stock
    """
    print(f"[DMART] Searching: {query}, pincode={pincode}, headful={headful}")

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
            print("[DMART] Opening homepage for location setup...")
            await page.goto(
                "https://www.dmart.in",
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            await page.wait_for_timeout(random.randint(3000, 5000))

            # Handle location / pincode modal
            await _set_location(page, pincode)

            # ── 2. Navigate to search results ────────────────────────
            search_url = f"https://www.dmart.in/search?searchTerm={quote_plus(query)}"
            print(f"[DMART] Opening: {search_url}")
            await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            await page.wait_for_timeout(random.randint(3000, 5000))

            # ── 3. Wait for products to appear ───────────────────────
            products_loaded = False
            for attempt in range(6):
                body_text = await page.inner_text("body")
                if "\u20B9" in body_text and "error 404" not in body_text.lower():
                    products_loaded = True
                    break
                await page.wait_for_timeout(2000)

            if not products_loaded:
                print("[DMART] Products did not load, checking for 404...")
                if "error 404" in body_text.lower():
                    print("[DMART] Got 404 — search URL may have changed")
                await _save_failure_dump(page)
                await browser.close()
                return results

            # ── 4. Scroll to load all products ───────────────────────
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(random.randint(300, 600))
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # ── 5. Extract products via JS ───────────────────────────
            raw_products = await page.evaluate("""() => {
                const gridItems = document.querySelectorAll('.MuiGrid-root.MuiGrid-item');
                const results = [];

                for (const item of gridItems) {
                    const text = item.innerText;
                    if (!text.includes('\\u20B9') || !text.includes('ADD TO CART')) continue;

                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                    // Image: first cdn.dmart.in image
                    let imageUrl = '';
                    const imgs = item.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.src && img.src.includes('cdn.dmart.in')) {
                            imageUrl = img.src;
                            break;
                        }
                    }
                    if (!imageUrl) {
                        // Try background-image divs
                        const bgDivs = item.querySelectorAll('div[style*="background-image"]');
                        for (const d of bgDivs) {
                            const style = d.getAttribute('style') || '';
                            const m = style.match(/url\\(["']?([^"')]+)["']?\\)/);
                            if (m && m[1].includes('cdn.dmart.in')) {
                                imageUrl = m[1];
                                break;
                            }
                        }
                    }

                    // Title from the image div's title attribute
                    let titleAttr = '';
                    const titledDivs = item.querySelectorAll('div[title]');
                    for (const d of titledDivs) {
                        const t = d.getAttribute('title');
                        if (t && t.length > 5) { titleAttr = t; break; }
                    }

                    results.push({ lines, imageUrl, titleAttr });
                }
                return results;
            }""")

            print(f"[DMART] Found {len(raw_products)} product cards")

            # ── 6. Parse structured fields from lines ────────────────
            for card in raw_products:
                product = _parse_card_lines(card["lines"], card["imageUrl"], card["titleAttr"])
                if product:
                    results.append(product)
                    if len(results) >= max_results:
                        break

        except Exception as exc:
            print(f"[DMART] Error: {exc}")
            import traceback
            traceback.print_exc()
            await _save_failure_dump(page)
        finally:
            await browser.close()

    print(f"[DMART] Returning {len(results)} results")
    return results


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _set_location(page, pincode: str) -> None:
    """Enter pincode in the location modal and click CONFIRM LOCATION."""
    pincode_input = await page.query_selector(
        "input#pincodeInput, input[placeholder*='pincode' i], input[placeholder*='PIN' i]"
    )
    if not pincode_input:
        print("[DMART] No pincode input found — location may already be set")
        return

    print(f"[DMART] Entering pincode: {pincode}")
    await pincode_input.fill(pincode)
    await page.wait_for_timeout(2000)

    # Select the first location suggestion
    location_buttons = await page.query_selector_all("ul[class*='p-0'] li button")
    if location_buttons:
        btn_text = (await location_buttons[0].inner_text()).strip()
        print(f"[DMART] Selecting location: {btn_text[:60]}")
        await location_buttons[0].click()
        await page.wait_for_timeout(3000)
    else:
        print("[DMART] No location suggestions appeared")

    # Click "CONFIRM LOCATION"
    confirm_btn = await page.query_selector(
        "button:has-text('CONFIRM LOCATION'), "
        "button:has-text('Confirm Location')"
    )
    if confirm_btn:
        print("[DMART] Clicking CONFIRM LOCATION")
        await confirm_btn.click()
        await page.wait_for_timeout(3000)
    else:
        # Fallback: try any green / primary button in the dialog
        modal_btns = await page.query_selector_all(
            ".MuiDialog-root button, .MuiModal-root button"
        )
        for btn in modal_btns:
            text = (await btn.inner_text()).strip().lower()
            if "confirm" in text:
                await btn.click()
                await page.wait_for_timeout(3000)
                break

    # Ensure modal is dismissed
    modal = await page.query_selector(".MuiDialog-root")
    if modal and await modal.is_visible():
        print("[DMART] Modal still visible, pressing Escape")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(2000)


def _parse_card_lines(
    lines: list,
    image_url: str,
    title_attr: str,
) -> dict | None:
    """
    Parse the fixed-order innerText lines of a product card.

    Expected order:
        [Out Of Stock]       ← optional
        Product Name
        MRP
        ₹ {mrp}
        DMart
        ₹ {sale}
        (Inclusive of all taxes)
        ₹ {discount}
        OFF
        {quantity}
        [(per-unit)]         ← optional
        ADD TO CART
    """
    if len(lines) < 6:
        return None

    idx = 0
    in_stock = True

    # Check for "Out Of Stock"
    if lines[idx].lower().startswith("out of stock"):
        in_stock = False
        idx += 1

    # Product name
    name = lines[idx] if idx < len(lines) else ""
    idx += 1

    # Prefer title attribute (more complete, no truncation)
    if title_attr and len(title_attr) > len(name):
        name = title_attr

    # Skip "MRP"
    if idx < len(lines) and lines[idx].upper() == "MRP":
        idx += 1

    # MRP price
    original_price = _extract_price(lines[idx]) if idx < len(lines) else None
    idx += 1

    # Skip "DMart"
    if idx < len(lines) and lines[idx].upper() == "DMART":
        idx += 1

    # Sale price
    sale_price = _extract_price(lines[idx]) if idx < len(lines) else None
    idx += 1

    # Skip "(Inclusive of all taxes)"
    if idx < len(lines) and "inclusive" in lines[idx].lower():
        idx += 1

    # Discount amount
    discount_amount = _extract_price(lines[idx]) if idx < len(lines) else None
    idx += 1

    # Skip "OFF"
    if idx < len(lines) and lines[idx].upper() == "OFF":
        idx += 1

    # Quantity
    quantity = ""
    if idx < len(lines) and lines[idx] != "ADD TO CART":
        quantity = lines[idx]
        idx += 1

    # Skip per-unit price line like "(₹ 48.20 / 1 kg)"
    if idx < len(lines) and lines[idx].startswith("(") and "₹" in lines[idx]:
        idx += 1

    if not name or sale_price is None:
        return None

    # Build discount string
    discount_str = ""
    if original_price and sale_price and original_price > sale_price:
        pct = round((original_price - sale_price) / original_price * 100)
        discount_str = f"{pct}% off (₹{discount_amount:.0f})" if discount_amount else f"{pct}% off"

    return {
        "name": name,
        "price": sale_price,
        "original_price": original_price,
        "discount": discount_str,
        "quantity": quantity,
        "image_url": image_url,
        "source": "dmart",
        "in_stock": in_stock,
    }


def _extract_price(text: str) -> float | None:
    """Pull the first decimal number out of a string like '₹ 241'."""
    if not text:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


async def _save_failure_dump(page) -> None:
    """Save a screenshot + HTML dump for post-mortem analysis."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ss_path = os.path.join(base, "dmart_failure_dump.png")
        html_path = os.path.join(base, "dmart_failure_dump.html")
        await page.screenshot(path=ss_path)
        content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[DMART] Saved failure screenshot to: {ss_path}")
        print(f"[DMART] Saved failure HTML to: {html_path}")
    except Exception:
        pass
