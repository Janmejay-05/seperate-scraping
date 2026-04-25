"""Quick test for the rewritten Blinkit scraper."""
import sys, os, asyncio
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.blinkit_scraper import search_blinkit

async def main():
    query = "sugar"
    pincode = "380015"
    max_results = 20

    print(f"\n{'='*60}")
    print(f" BLINKIT SCRAPER TEST: '{query}', pincode={pincode}")
    print(f"{'='*60}")
    try:
        results = await search_blinkit(
            query=query, pincode=pincode,
            max_results=max_results, headful=True,
        )
        print(f"\nBlinkit returned {len(results)} results:\n")
        for i, r in enumerate(results):
            print(f"  [{i+1:2d}] {r['name'][:55]}")
            print(f"       Price: ₹{r['price']}  |  MRP: ₹{r.get('original_price', 'N/A')}  |  {r.get('discount', '')}")
            print(f"       Qty: {r.get('quantity', 'N/A')}  |  Source: {r.get('source', 'N/A')}")
            print(f"       Image: {(r.get('image_url') or 'N/A')[:70]}")
            print()

        # Write results as JSON for easy inspection
        import json
        with open("blinkit_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Full results written to blinkit_results.json")

    except Exception as e:
        print(f"Blinkit FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
