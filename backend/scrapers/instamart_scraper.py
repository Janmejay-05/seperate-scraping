# backend/scrapers/instamart_scraper.py

from playwright.async_api import async_playwright
import asyncio
import random
import re
import os
import json



async def rand_delay(a=0.3, b=1.0):
    await asyncio.sleep(random.uniform(a, b))


STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
delete navigator.__proto__.webdriver;
"""


def extract_quantity(text: str):
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


def _lat_lng_to_address(lat: float, lng: float) -> str:
    """Return a city name based on approximate lat/lng coordinates."""
    # Common Indian city coordinates (approximate)
    cities = [
        (23.0225, 72.5714, "Ahmedabad, Gujarat"),
        (19.0760, 72.8777, "Mumbai, Maharashtra"),
        (28.6139, 77.2090, "New Delhi, Delhi"),
        (12.9716, 77.5946, "Bangalore, Karnataka"),
        (13.0827, 80.2707, "Chennai, Tamil Nadu"),
        (17.3850, 78.4867, "Hyderabad, Telangana"),
        (22.5726, 88.3639, "Kolkata, West Bengal"),
        (18.5204, 73.8567, "Pune, Maharashtra"),
        (26.9124, 75.7873, "Jaipur, Rajasthan"),
        (21.1702, 72.8311, "Surat, Gujarat"),
    ]
    
    best_city = "India"
    best_dist = float('inf')
    for city_lat, city_lng, city_name in cities:
        dist = abs(lat - city_lat) + abs(lng - city_lng)
        if dist < best_dist:
            best_dist = dist
            best_city = city_name
    
    return best_city


def _parse_products_from_text(body_text: str, max_results: int = 20):
    """
    Parse products from the visible page text.
    
    Instamart renders product cards with this text pattern:
        [X MINS]
        [Product Name]
        [Description (optional)]
        [Quantity e.g. "1 kg"]
        [Discount e.g. "33% OFF"]
        [Sale Price (number)]
        [Original Price (number, strikethrough)]
        
    Products may also have "Ad" label preceding them.
    """
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]
    
    products = []
    i = 0
    while i < len(lines) and len(products) < max_results:
        line = lines[i]
        
        # Look for delivery time pattern "X MINS" - this starts a product block
        if re.match(r'^\d+\s*MINS?$', line, re.I):
            # Possibly an "Ad" label right before
            is_ad = (i > 0 and lines[i - 1].strip().lower() == "ad")
            
            # Skip the delivery time line
            j = i + 1
            
            # Next non-empty, non-delivery line should be the product name
            name = None
            description = None
            quantity = None
            discount = None
            sale_price = None
            original_price = None
            
            while j < len(lines) and j < i + 10:
                l = lines[j].strip()
                
                # Another delivery time means next product
                if re.match(r'^\d+\s*MINS?$', l, re.I):
                    break
                
                # Skip "Ad" labels
                if l.lower() == "ad":
                    j += 1
                    continue
                
                # Discount pattern
                if re.match(r'^\d+%\s*OFF$', l, re.I):
                    discount = l
                    j += 1
                    continue
                
                # Quantity pattern (e.g. "1 kg", "500 ml", "250 g")
                if re.match(r'^\d+(?:\.\d+)?\s*(kg|g|gm|ml|l|litre|ltr|pcs?|pack|piece)s?$', l, re.I):
                    quantity = l
                    j += 1
                    continue
                
                # Pure number — this is a price
                if re.match(r'^\d+(?:\.\d+)?$', l):
                    if sale_price is None:
                        sale_price = float(l)
                    elif original_price is None:
                        original_price = float(l)
                    j += 1
                    continue
                    
                # Price with ₹ symbol
                price_match = re.match(r'^₹\s*(\d+(?:\.\d+)?)', l)
                if price_match:
                    if sale_price is None:
                        sale_price = float(price_match.group(1))
                    elif original_price is None:
                        original_price = float(price_match.group(1))
                    j += 1
                    continue
                
                # Product name (first substantial text line)
                if name is None and len(l) > 3:
                    name = l
                    j += 1
                    continue
                
                # Description (second text line after name)
                if name and description is None and len(l) > 3:
                    description = l
                    j += 1
                    continue
                
                j += 1
            
            if name and sale_price is not None:
                products.append({
                    "name": name,
                    "price": sale_price,
                    "original_price": original_price,
                    "quantity": quantity,
                    "discount": discount,
                    "description": description,
                    "is_ad": is_ad,
                })
            
            # Move to the next product block
            i = j
        else:
            i += 1
    
    return products


async def search_instamart(
    query: str,
    lat: float = 23.0225,
    lng: float = 72.5714,
    max_results: int = 20,
    headful: bool = False,
    timeout: int = 60000
):
    """
    Search Swiggy Instamart for products using async Playwright.
    
    Note: Swiggy requires location to be set before search will work.
    This function sets location via localStorage and cookies before navigating.
    """
    print(f"[INSTAMART] Searching: {query}, lat={lat}, lng={lng}, headful={headful}")
    
    results = []
    address = _lat_lng_to_address(lat, lng)
    city = address.split(",")[0].strip()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headful,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )
        
        context = await browser.new_context(
            locale="en-IN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            geolocation={"latitude": lat, "longitude": lng},
            permissions=["geolocation"],
            bypass_csp=True,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )
        
        # Don't abort all images, some might be needed for layout/detection
        await context.route("**/*.{ico,woff,woff2}", lambda route: route.abort())
        
        page = await context.new_page()
        await page.add_init_script(STEALTH_JS)
        
        try:
            # ── Step 1: Visit swiggy.com and set location ──
            print("[INSTAMART] Setting location...")
            await page.goto("https://www.swiggy.com", wait_until="domcontentloaded", timeout=timeout)
            await rand_delay(1, 2)
            
            # Set localStorage items for location
            await page.evaluate(f"""() => {{
                localStorage.setItem('lat', '{lat}');
                localStorage.setItem('lng', '{lng}');
                localStorage.setItem('userLocation', JSON.stringify({{
                    lat: {lat},
                    lng: {lng},
                    address: '{address}',
                    area: '{city}',
                    city: '{city}'
                }}));
                localStorage.setItem('address', '{address}');
                localStorage.setItem('city', '{city}');
                localStorage.setItem('addressId', '');
            }}""")
            
            # Set cookies
            await context.add_cookies([
                {"name": "lat", "value": str(lat), "domain": ".swiggy.com", "path": "/"},
                {"name": "lng", "value": str(lng), "domain": ".swiggy.com", "path": "/"},
                {"name": "userLocation", "value": json.dumps({"lat": lat, "lng": lng, "address": address}), "domain": ".swiggy.com", "path": "/"},
                {"name": "addressId", "value": "", "domain": ".swiggy.com", "path": "/"},
            ])
            
            # ── Step 2: Visit Instamart home to establish session ──
            print("[INSTAMART] Visiting Instamart home...")
            await page.goto("https://www.swiggy.com/instamart", wait_until="domcontentloaded", timeout=timeout)
            await rand_delay(2, 4)
            
            # Handle location picker if shown
            body_text = await page.inner_text("body")
            if any(kw in body_text.lower() for kw in ["detect my location", "enter your delivery"]):
                print("[INSTAMART] Location picker detected, trying to auto-detect...")
                detect_btn = await page.query_selector('button:has-text("Detect"), button:has-text("Use current")')
                if detect_btn:
                    await detect_btn.click()
                    await rand_delay(3, 5)

            # ── Step 3: Navigate to search ──
            search_url = f"https://www.swiggy.com/instamart/search?query={query}"
            print(f"[INSTAMART] Opening: {search_url}")
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
            await rand_delay(3, 5)
            
            # Wait for products to load with retry
            products_loaded = False
            for attempt in range(5):
                body_text = await page.inner_text("body")
                has_content = len(body_text) > 500
                has_error = "something went wrong" in body_text.lower() or "try again" in body_text.lower()
                
                if has_content and not has_error:
                    products_loaded = True
                    print(f"[INSTAMART] Content loaded ({len(body_text)} chars)")
                    break
                    
                if has_error:
                    print(f"[INSTAMART] Error page detected (attempt {attempt + 1}), retrying...")
                    try:
                        try_btn = await page.query_selector('[data-testid="error-button"], button:has-text("Try Again")')
                        if try_btn:
                            await try_btn.click()
                            await rand_delay(3, 5)
                    except:
                        pass
                    
                    # If retry fails, try re-navigating
                    if attempt >= 2:
                        await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)
                        await rand_delay(3, 5)
                else:
                    await rand_delay(2, 3)
            
            if not products_loaded:
                print("[INSTAMART] Failed to load products after retries")
                await _save_failure_dump(page)
                await browser.close()
                return []
            
            # ── Step 4: Scroll to load more products ──
            print("[INSTAMART] Scrolling to load more products...")
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 600)")
                await rand_delay(0.5, 1)
            
            # Scroll back up
            await page.evaluate("window.scrollTo(0, 0)")
            await rand_delay(0.5, 1)
            
            # ── Step 5: Extract products from visible text ──
            body_text = await page.inner_text("body")
            print(f"[INSTAMART] Extracting from {len(body_text)} chars of text...")
            
            parsed = _parse_products_from_text(body_text, max_results=max_results)
            print(f"[INSTAMART] Parsed {len(parsed)} products from text")
            
            for i, product in enumerate(parsed):
                if len(results) >= max_results:
                    break
                
                # Skip ad products
                if product.get("is_ad"):
                    print(f"[INSTAMART] Skipping ad product: {product['name']}")
                    continue
                
                # Build quantity info
                qty_info = extract_quantity(
                    product.get("quantity", "") or product.get("name", "")
                )
                qty_display = product.get("quantity") or ""
                
                results.append({
                    "id": f"instamart_{i}",
                    "name": product["name"],
                    "price": product["price"],
                    "original_price": product.get("original_price"),
                    "quantity": qty_display,
                    "discount": product.get("discount"),
                    "link": "",
                    "image": "",
                    "platform": "Instamart"
                })
            
            if not results:
                print("[INSTAMART] No products extracted!")
                await _save_failure_dump(page)

        except Exception as e:
            print(f"[INSTAMART] Error: {e}")
            try:
                await _save_failure_dump(page)
            except:
                pass
            import traceback
            traceback.print_exc()
        
        finally:
            await browser.close()
    
    print(f"[INSTAMART] Returning {len(results)} results")
    return results


async def _save_failure_dump(page):
    """Save screenshot and HTML dump for debugging."""
    try:
        screenshot_path = os.path.join(os.getcwd(), "instamart_failure_dump.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"[INSTAMART] Saved failure screenshot to: {screenshot_path}")
        
        html_path = os.path.join(os.getcwd(), "instamart_failure_dump.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(await page.content())
        print(f"[INSTAMART] Saved failure HTML to: {html_path}")
    except Exception as e:
        print(f"[INSTAMART] Error saving failure dump: {e}")
