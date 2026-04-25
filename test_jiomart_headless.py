"""Test JioMart scraper in HEADLESS mode (as the server runs it)."""
import sys, os, asyncio
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.jiomart_scraper import search_jiomart

async def main():
    print("=== Testing JioMart HEADLESS ===")
    results = await search_jiomart(query="sugar", pincode="380015", max_results=10, headful=False)
    print(f"\nReturned {len(results)} results")
    for i, r in enumerate(results[:5]):
        print(f"  [{i+1}] {r['name'][:60]}  ₹{r['price']}  img={'YES' if r.get('image_url') else 'NO'}")

if __name__ == "__main__":
    asyncio.run(main())
