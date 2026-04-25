# backend/app.py

"""
FastAPI application for Quick Compare - Product Price Comparison.
"""

import sys
import asyncio

# Fix for Playwright on Windows: Force ProactorEventLoop
# Must be unconditional — uvicorn worker processes may not inherit the policy from run.py
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import unquote
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import httpx

from backend.database import get_db, init_db, Product, PriceHistory
from backend.scrapers.search_all import search_all, normalize_product_name


# =====================
# Pydantic Models
# =====================

class SearchRequest(BaseModel):
    query: str
    pincode: str = "380015"
    lat: float = 23.0225
    lng: float = 72.5714
    max_results: int = 40
    headful: bool = False


class ProductResponse(BaseModel):
    id: int
    name: str
    platform: str
    price: Optional[float]
    quantity: Optional[str]
    unit_price: Optional[float]
    link: Optional[str]
    scraped_at: Optional[datetime]

    class Config:
        from_attributes = True


# =====================
# Scheduler
# =====================

scheduler = AsyncIOScheduler()
tracked_queries = []


async def scheduled_scrape_job():
    """Re-scrape all tracked queries."""
    print(f"[SCHEDULER] Running scheduled scrape at {datetime.now()}")
    
    for query_info in tracked_queries:
        try:
            results = await search_all(
                query=query_info['query'],
                pincode=query_info.get('pincode', '380015'),
                lat=query_info.get('lat', 23.0225),
                lng=query_info.get('lng', 72.5714),
                max_results=20,
                headful=False
            )
            
            print(f"[SCHEDULER] Scraped {len(results.get('all_results', []))} results for '{query_info['query']}'")
            
        except Exception as e:
            print(f"[SCHEDULER] Error scraping '{query_info['query']}': {e}")


# =====================
# Lifespan
# =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("[APP] Initializing database...")
    init_db()
    
    print("[APP] Starting scheduler...")
    scheduler.add_job(
        scheduled_scrape_job,
        IntervalTrigger(days=1),
        id='daily_scrape',
        name='Daily Product Scrape',
        replace_existing=True
    )
    scheduler.start()
    
    yield
    
    print("[APP] Shutting down scheduler...")
    scheduler.shutdown()


# =====================
# FastAPI App
# =====================

app = FastAPI(
    title="Quick Compare API",
    description="Compare product prices across DMart, JioMart, Blinkit, and Instamart",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# (Frontend setup moved to end of file)


# =====================
# API Endpoints
# =====================

# Allowed image CDN host patterns (security: only proxy known CDNs)
_ALLOWED_IMAGE_HOSTS = (
    "www.jiomart.com",
    "cdn.grofers.com",          # Blinkit CDN
    "cdn.dmart.in",
    "blinkit.com",
    "instamart.com",
    "media-assets.swiggy.com",
    "cdn.zeptonow.com",
    "m.media-amazon.com",
)

@app.get("/api/image-proxy")
async def image_proxy(url: str = Query(..., description="Image URL to proxy")):
    """
    Proxy product images so the browser doesn't send a Referer header
    that CDNs use to block hotlinking.
    """
    decoded = unquote(url)

    # Basic validation
    if not decoded.startswith("https://"):
        raise HTTPException(400, "Only HTTPS URLs are allowed")

    from urllib.parse import urlparse
    host = urlparse(decoded).hostname or ""
    if not any(host.endswith(h) for h in _ALLOWED_IMAGE_HOSTS):
        raise HTTPException(403, f"Host not allowed: {host}")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(decoded, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
                "Accept": "image/*,*/*;q=0.8",
            })
            if resp.status_code != 200:
                raise HTTPException(502, f"Upstream returned {resp.status_code}")

            content_type = resp.headers.get("content-type", "image/jpeg")
            return StreamingResponse(
                iter([resp.content]),
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},  # cache 24h
            )
    except httpx.TimeoutException:
        raise HTTPException(504, "Image fetch timed out")
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch image: {e}")

# (API endpoints continue below...)


@app.post("/api/search")
async def search_products(request: SearchRequest):
    """
    Search products across all platforms.
    """
    try:
        results = await search_all(
            query=request.query,
            pincode=request.pincode,
            lat=request.lat,
            lng=request.lng,
            max_results=request.max_results,
            headful=request.headful
        )
        
        # Track query
        query_info = {
            "query": request.query,
            "pincode": request.pincode,
            "lat": request.lat,
            "lng": request.lng
        }
        if query_info not in tracked_queries:
            tracked_queries.append(query_info)
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products")
async def list_products(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List all tracked products."""
    products = db.query(Product).offset(skip).limit(limit).all()
    return {"products": products, "total": db.query(Product).count()}


@app.get("/api/products/{product_id}")
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get product with price history."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    price_history = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id
    ).order_by(PriceHistory.scraped_at.desc()).all()
    
    return {"product": product, "price_history": price_history}


@app.get("/api/compare")
async def compare_products(
    query: str = Query(..., description="Product name to compare"),
    db: Session = Depends(get_db)
):
    """Compare a product across platforms."""
    from fuzzywuzzy import fuzz
    
    normalized_query = normalize_product_name(query)
    
    recent_prices = db.query(PriceHistory).order_by(
        PriceHistory.scraped_at.desc()
    ).limit(500).all()
    
    matches = []
    for price in recent_prices:
        product = db.query(Product).filter(Product.id == price.product_id).first()
        if product:
            similarity = fuzz.token_set_ratio(normalized_query, product.normalized_name or "")
            if similarity >= 70:
                matches.append({
                    "product": product,
                    "price_info": price,
                    "similarity": similarity
                })
    
    matches.sort(key=lambda x: (-x['similarity'], x['price_info'].unit_price or 999999))
    
    return {"query": query, "matches": matches[:20]}


@app.get("/api/health")
async def health_check():
    """Health check."""
    return {
        "status": "healthy",
        "scheduler_running": scheduler.running,
        "tracked_queries": len(tracked_queries)
    }

# =====================
# Frontend Serving
# =====================

# Resolve FRONTEND_DIR relative to this file's location
# backend/app.py -> backend -> root -> frontend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

print(f"[APP] Searching for frontend at: {FRONTEND_DIR}")
print(f"[APP] Directory exists: {os.path.exists(FRONTEND_DIR)}")

@app.get("/")
async def serve_home():
    """Explicitly serve index.html for the root URL."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "Frontend files missing", "searched_at": FRONTEND_DIR}

# Serve remaining static files (CSS, JS, etc.)
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
