
import sys
import asyncio
import os

# Fix for Playwright on Windows: Force ProactorEventLoop
if sys.platform == 'win32':
    try:
        if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.scrapers.jiomart_scraper import search_jiomart

async def run_test():
    print("Testing JioMart Scraper...")
    try:
        results = await search_jiomart("sugar", max_results=100, headful=True)
        print(f"Found {len(results)} results.")
        for item in results:
            print(f"- {item['name']} : {item['price']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
