"""Quick test for the rewritten JioMart scraper."""
import sys, os, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.jiomart_scraper import search_jiomart

async def main():
    results = await search_jiomart(query="sugar", pincode="380015", max_results=20, headful=True)
    print(f"\nJioMart returned {len(results)} results:\n")
    for i, r in enumerate(results):
        print(f"  [{i+1:2d}] {r['name'][:55]}")
        print(f"       Price: ₹{r['price']}  |  MRP: ₹{r.get('original_price', 'N/A')}  |  {r.get('discount', '')}")
        print(f"       Qty: {r.get('quantity', 'N/A')}  |  Source: {r.get('source', 'N/A')}")
        print(f"       Image: {(r.get('image_url') or 'N/A')[:70]}")
        print()
    
    with open("jiomart_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Full results written to jiomart_results.json")

if __name__ == "__main__":
    asyncio.run(main())
