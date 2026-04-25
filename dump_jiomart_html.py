# import asyncio
# from playwright.async_api import async_playwright
# import sys

# if sys.platform == 'win32':
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# async def dump_html():
#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=False)
#         context = await browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
#         )
#         page = await context.new_page()
#         print("Navigating to JioMart...")
#         await page.goto("https://www.jiomart.com/search/sugar", timeout=60000)
#         print("Waiting 15s for content...")
#         await page.wait_for_timeout(15000)
        
#         # Check for modals or overlays
#         print("Checking for location modal...")
#         try:
#             # Try specific selectors for location/pincode modal
#             modal = await page.query_selector("div.delivery-location-container, div.location_box, div.delivery-location")
#             if modal:
#                 print("Location modal found!")
#                 # Try to close it if possible
#                 close_btn = await page.query_selector("button.close-btn, button[aria-label='Close'], div.location-close-btn")
#                 if close_btn:
#                     print("Found close button, clicking...")
#                     await close_btn.click()
#                     await page.wait_for_timeout(2000)
#                 else:
#                     print("No close button found for modal.")
#             else:
#                 print("No obvious location modal found.")
#         except Exception as e:
#             print(f"Error checking modal: {e}")

#         # specific check for product list
#         print("Checking for products...")
#         products = await page.query_selector_all("li[class*='ais-Hits'], div[class*='plp-card'], div.product-card")
#         print(f"Found {len(products)} products with known selectors.")
        
#         if len(products) == 0:
#             print("Trying generic product card search...")
#             # Try to find anything that looks like a product card
#             cards = await page.query_selector_all("div[class*='card'], .product-item")
#             print(f"Generic search found {len(cards)} potential cards.")

#         body_text = await page.inner_text("body")
#         print(f"Body Text Preview: {body_text[:500]}")
        
#         content = await page.content()
#         with open("jiomart_dump.html", "w", encoding="utf-8") as f:
#             f.write(content)
#         print("HTML dumped to jiomart_dump.html")
        
#         # Also take a screenshot
#         await page.screenshot(path="jiomart_dump.png")
#         print("Screenshot saved to jiomart_dump.png")
        
#         await browser.close()

# if __name__ == "__main__":
#     asyncio.run(dump_html())

import asyncio
import sys
import re
from urllib.parse import quote_plus
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def scrape_jiomart_search(query: str, max_results: int = 20):
    search_url = f"https://www.jiomart.com/search/?q={quote_plus(query)}"
    print(f"[TEST] Opening: {search_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[TEST] Navigation error: {e}")
            await browser.close()
            return

        try:
            await page.wait_for_selector(
                "div.plp-card, li[class*='ais-Hits'], div.product-card",
                timeout=30000,
            )
            print("[TEST] Product cards appeared.")
        except PlaywrightTimeoutError:
            print("[TEST] No product cards found within timeout.")
            await browser.close()
            return

        products = await page.query_selector_all(
            "div.plp-card, li[class*='ais-Hits'], div.product-card"
        )
        print(f"[TEST] Found {len(products)} product elements.")

        results = []

        for product in products[:max_results]:
            try:
                name = await get_product_name(product)
                price = await get_product_price(product)
                link = await get_product_link(product)

                if not name or price is None:
                    continue

                if link and not link.startswith("http"):
                    link = "https://www.jiomart.com" + link

                results.append(
                    {
                        "name": name,
                        "price": price,
                        "link": link,
                    }
                )
            except Exception as e:
                print(f"[TEST] Error parsing product: {e}")
                continue

        print(f"[TEST] Returning {len(results)} products for query='{query}':")
        for idx, item in enumerate(results, start=1):
            print(f"{idx}. {item['name']} | ₹{item['price']} | {item['link']}")

        await browser.close()


async def get_product_name(product_element):
    for sel in [".plp-name", ".product-name", "a", "h2", "h3"]:
        el = await product_element.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            if text:
                return text
    text_content = await product_element.inner_text()
    lines = [l.strip() for l in text_content.split("\n") if l.strip()]
    return lines[0] if lines else None


async def get_product_price(product_element):
    for sel in [".plp-price", ".price", ".offer-price", ".mrp"]:
        el = await product_element.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            match = re.search(r"₹\s*(\d+(?:\.\d+)?)", text)
            if match:
                return float(match.group(1))
    text_content = await product_element.inner_text()
    match = re.search(r"₹\s*(\d+(?:\.\d+)?)", text_content)
    if match:
        return float(match.group(1))
    return None


async def get_product_link(product_element):
    for sel in ["a[href*='/p/']", "a[href]"]:
        el = await product_element.query_selector(sel)
        if el:
            href = await el.get_attribute("href")
            if href:
                return href
    return await product_element.get_attribute("href")


if __name__ == "__main__":
    asyncio.run(scrape_jiomart_search("sugar"))
