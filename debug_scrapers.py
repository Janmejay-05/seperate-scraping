
import asyncio
import json
from backend.scrapers.search_all import search_all

async def run_debug():
    print("Running debug search...")
    results = await search_all("soap", max_results=1, headful=False)
    
    print("\n\n=== ERRORS ===")
    for err in results.get('errors', []):
        print(f"Platform: {err['platform']}")
        print(f"Error: {err['error']}\n")
        
    print("\n\n=== RESULTS ===")
    print(json.dumps(results.get('all_results', []), indent=2))

if __name__ == "__main__":
    asyncio.run(run_debug())
