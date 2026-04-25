from playwright.sync_api import sync_playwright
import random, time

def rand_delay(a=0.3, b=1.0):
    time.sleep(random.uniform(a, b))

def _safe(elem):
    try:
        return elem.inner_text().strip()
    except:
        return None

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => false});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
"""

def search_zomato(
    query: str,
    city: str = "Ahmedabad",
    max_results: int = 20,
    headful: bool = True,
    fetch_menu: bool = False,
    timeout: int = 60000
):
    print(f"[ZOMATO] headful={headful}, fetch_menu={fetch_menu}")

    results = []
    city_slug = city.lower().replace(" ", "-")
    base_url = f"https://www.zomato.com/{city_slug}/restaurants"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headful,
            args=["--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120 Mobile Safari/537.36"
            ),
            viewport={"width": 412, "height": 915}
        )

        page = context.new_page()
        page.add_init_script(STEALTH_JS)

        print("[ZOMATO] Opening restaurants page...")
        page.goto(base_url, wait_until="networkidle", timeout=timeout)

        # ----------------------------
        # CLICK SEARCH BAR (LATEST FIX)
        # ----------------------------
                # ----------------------------
        # CLICK SEARCH BAR (React hydration-safe)
        # ----------------------------
                # ----------------------------
        # CLICK SEARCH BAR (React hydration-safe, sync version)
        # ----------------------------
                # --------------------------------------
        # NEW: Direct URL search (no UI clicking)
        # --------------------------------------
                # --------------------------------------
        # NEW: Direct URL search (no UI clicking)
        # --------------------------------------
        try:
            search_url = f"https://www.zomato.com/{city_slug}/restaurants?q={query}"
            print("[ZOMATO] Opening direct search URL:", search_url)

            page.goto(search_url, wait_until="networkidle", timeout=timeout)
            rand_delay(3, 4)

        except Exception as e:
            print("[ZOMATO] Direct URL search failed →", e)
            page.screenshot(path="debug_direct_search_fail.png")
            browser.close()
            return []


        # ----------------------------
        # SCROLL TO LOAD RESULTS
        # ----------------------------
        print("[ZOMATO] Scrolling...")
        for _ in range(6):
            page.mouse.wheel(0, 2000)
            rand_delay(0.4, 0.9)

        # Parse restaurant cards
        cards = page.query_selector_all("div.sc-1mo3ldo-0")
        print(f"[ZOMATO] Found {len(cards)} cards")

        for c in cards[:max_results]:
            try:
                name = _safe(c.query_selector("h4"))
                price = _safe(c.query_selector("p:has-text('for two')"))
                rating = _safe(c.query_selector("div[aria-label*='rating']"))

                link = None
                a = c.query_selector("a")
                if a:
                    link = a.get_attribute("href")
                    if link and link.startswith("/"):
                        link = "https://www.zomato.com" + link
            except:
                continue

            item = {
                "platform": "Zomato",
                "name": name,
                "rating": rating,
                "price": price,
                "link": link,
                "menu": None
            }

            # ----------------------------
            # FETCH MENU (OPTIONAL)
            # ----------------------------
            if fetch_menu and link:
                try:
                    pg2 = context.new_page()
                    pg2.goto(link, wait_until="networkidle", timeout=timeout)
                    rand_delay(1, 2)

                    items = pg2.query_selector_all("h4, h3")
                    menu_list = [_safe(m) for m in items if _safe(m)]
                    item["menu"] = menu_list[:50]

                    pg2.close()
                except:
                    item["menu"] = []

            results.append(item)

        browser.close()
        return results
