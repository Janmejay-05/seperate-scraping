"""Quick test for the rewritten DMart scraper."""
import sys, os, asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.dmart_scraper import search_dmart

async def main():
    query = "sugar"
    pincode = "380015"
    max_results = 20

    print(f"\n{'='*60}")
    print(f" DMART SCRAPER TEST: '{query}', pincode={pincode}")
    print(f"{'='*60}")
    try:
        results = await search_dmart(
            query=query, pincode=pincode,
            max_results=max_results, headful=True,
        )
        print(f"\nDMart returned {len(results)} results:\n")
        for i, r in enumerate(results):
            stock = "IN STOCK" if r.get("in_stock", True) else "OUT OF STOCK"
            print(f"  [{i+1:2d}] {r['name'][:55]}")
            print(f"       Price: Rs.{r['price']}  |  MRP: Rs.{r.get('original_price', 'N/A')}  |  {r.get('discount', '')}")
            print(f"       Qty: {r.get('quantity', 'N/A')}  |  {stock}")
            print(f"       Image: {r.get('image_url', 'N/A')[:70]}")
            print()
    except Exception as e:
        print(f"DMart FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
