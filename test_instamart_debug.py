"""Quick test for the rewritten Instamart scraper."""
import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.instamart_scraper import search_instamart

async def main():
    query = "sugar"
    lat, lng = 23.0225, 72.5714
    max_results = 20

    print(f"\n{'='*50}")
    print(f"TESTING INSTAMART: {query}")
    print(f"{'='*50}")
    try:
        results = await search_instamart(
            query=query, lat=lat, lng=lng,
            max_results=max_results, headful=True
        )
        print(f"\nInstamart returned {len(results)} results:")
        for i, r in enumerate(results):
            print(f"  [{i+1}] {r['name']}: Rs.{r['price']} | Qty: {r.get('quantity', 'N/A')} | Discount: {r.get('discount', 'N/A')}")
    except Exception as e:
        print(f"Instamart failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
