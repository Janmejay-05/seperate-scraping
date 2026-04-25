# Quick Compare - Product Price Comparison

A full-stack application to compare product prices across DMart, JioMart, Blinkit, and Instamart.

## Architecture

- **Backend**: FastAPI (Python) - Handles scraping, database, and API.
- **Frontend**: Vanilla HTML/JS/CSS - Served by FastAPI.
- **Database**: SQLite (via SQLAlchemy).

## Prerequisites

- Python 3.8+
- Playwright (for scraping)

## Setup

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/Mac
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

## Running the App

1. **Start the application**:
   ```bash
   python run.py
   ```

2. **Access the application**:
   Open you web browser and navigate to:
   [http://localhost:8000](http://localhost:8000)

   **Note**: Do NOT open `index.html` directly from the file system. It requires the backend to function.

## Development

- Backend code is in `backend/`.
- Frontend code is in `frontend/`.
- Scrapers are located in `backend/scrapers/`.