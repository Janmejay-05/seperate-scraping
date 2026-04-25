# backend/scrapers/swiggy_scraper.py

from playwright.sync_api import sync_playwright
import time, random

def rand_delay(a=0.2, b=0.5):
    time.sleep(random.uniform(a, b))

def _safe(elem):
    try:
        return elem.inner_text().strip()
    except:
        return None

def search_swiggy(
    query: str,
    city: str = "Ahmedabad",
    max_results: int = 20,
    headful: bool = True
):
    print(f"[SWIGGY] headful={headful}, city={city}")

    # Fixed geo coordinates for Ahmedabad
    lat = 23.0225
    lng = 72.5714
    url = f"https://www.swiggy.com/search?lat={lat}&lng={lng}&query={query}"

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(
            viewport={"width": 1300, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            )
        )
        page = context.new_page()

        print("[SWIGGY] Opening:", url)
        page.goto(url, wait_until="networkidle", timeout=60000)
        rand_delay(1, 2)

        print("[SWIGGY] Scrolling...")
        for _ in range(8):
            page.mouse.wheel(0, 1800)
            rand_delay()

        # 🔥 NEW Swiggy card selector (root container)
        cards = page.query_selector_all("div._2DMsY._1bawW, div._2DMsY")

        print(f"[SWIGGY] Found {len(cards)} cards")

        for c in cards[:max_results]:
            try:
                # Restaurant Name
                name = _safe(c.query_selector("div._1b5YC"))
                if not name or len(name) < 2:
                    continue

                # Rating
                rating = _safe(c.query_selector("span._3Mn31")) \
                    or _safe(c.query_selector("div._3Mn31"))

                # ETA
                eta = _safe(c.query_selector("div._1JIkP"))

                # Price / Cost for two
                price = _safe(c.query_selector("div._3zbCR"))

                # Link inside <a>
                link_elem = c.query_selector("a")
                link = None
                if link_elem:
                    link = link_elem.get_attribute("href")
                    if link.startswith("/"):
                        link = "https://www.swiggy.com" + link

                results.append({
                    "platform": "Swiggy",
                    "name": name,
                    "rating": rating,
                    "eta": eta,
                    "price": price,
                    "link": link
                })

            except Exception as e:
                print("[SWIGGY] Error reading card:", e)
                continue

        browser.close()
        return results
