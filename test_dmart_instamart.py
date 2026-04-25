"""Verify DMart and Instamart scrapers using backend functions."""
import sys
import os
import asyncio
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.scrapers.dmart_scraper import search_dmart
from backend.scrapers.instamart_scraper import search_instamart

async def main():
    query = "sugar"
    pincode = "380015"
    lat, lng = 23.0225, 72.5714
    max_results = 5
    headful = True # Run headfully to see what's happening

    print(f"\n{'='*50}")
    print(f"TESTING DMART: {query}")
    print(f"{'='*50}")
    try:
        dmart_results = await search_dmart(query=query, pincode=pincode, max_results=max_results, headful=headful)
        print(f"\nDMart returned {len(dmart_results)} results:")
        for r in dmart_results:
            print(f"- {r['name']}: ₹{r['price']} ({r['quantity']})")
    except Exception as e:
        print(f"DMart failed: {e}")

    print(f"\n{'='*50}")
    print(f"TESTING INSTAMART: {query}")
    print(f"{'='*50}")
    try:
        instamart_results = await search_instamart(query=query, lat=lat, lng=lng, max_results=max_results, headful=headful)
        print(f"\nInstamart returned {len(instamart_results)} results:")
        for r in instamart_results:
            print(f"- {r['name']}: ₹{r['price']} ({r['quantity']})")
    except Exception as e:
        print(f"Instamart failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
