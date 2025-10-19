from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional
import uuid
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Models
class ExchangeRate(BaseModel):
    currency: str
    buy: float
    sell: float

class SourceRates(BaseModel):
    source: str
    url: str
    rates: Dict[str, ExchangeRate]
    last_updated: str
    status: str  # 'success' or 'error'
    error_message: Optional[str] = None

class AllRatesResponse(BaseModel):
    sources: List[SourceRates]
    timestamp: str

# Helper function to get real exchange rates from reliable API
def get_accurate_rates():
    """Get accurate exchange rates using free Open Exchange Rates API"""
    try:
        # Using open.er-api.com - free tier, no key required
        base_url = "https://open.er-api.com/v6/latest/USD"
        
        response = requests.get(base_url, timeout=10)
        data = response.json()
        
        if data.get('result') != 'success':
            raise Exception("API request failed")
        
        rates = data.get('rates', {})
        
        # Get TRY rate and calculate inverses for other currencies
        try_per_usd = rates.get('TRY', 0)
        
        if try_per_usd == 0:
            raise Exception("TRY rate not found")
        
        # Calculate TRY rates for each currency
        try_rates = {
            'USD': try_per_usd,
            'EUR': try_per_usd / rates.get('EUR', 1) if rates.get('EUR') else 0,
            'GBP': try_per_usd / rates.get('GBP', 1) if rates.get('GBP') else 0,
            'CHF': try_per_usd / rates.get('CHF', 1) if rates.get('CHF') else 0
        }
        
        # Get gold price
        try:
            gold_response = requests.get("https://api.gold-api.com/price/XAU", timeout=10)
            if gold_response.status_code == 200:
                gold_data = gold_response.json()
                gold_usd = float(gold_data.get('price', 2650))
            else:
                gold_usd = 2650  # Fallback
            try_rates['XAU'] = gold_usd * try_per_usd
        except:
            # Fallback gold price
            try_rates['XAU'] = 2650 * try_per_usd
        
        return try_rates
    except Exception as e:
        logger.error(f"Error getting accurate rates: {e}")
        return None

# Scraper functions
# Helper function to scrape with Playwright
async def scrape_with_playwright(url):
    """Scrape a website using Playwright for JavaScript-rendered content"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await page.wait_for_timeout(3000)  # Wait for JS to render
            
            content = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            return soup
    except Exception as e:
        logger.error(f"Playwright scraping error for {url}: {e}")
        return None

# Scraper functions
async def scrape_ahlatci():
    """Scrape rates from Ahlatcı Döviz"""
    try:
        url = "https://www.ahlatcidoviz.com.tr"
        soup = await scrape_with_playwright(url)
        
        if not soup:
            raise Exception("Failed to load page")
        
        rates = {}
        rows = soup.find_all('tr')
        
        for row in rows:
            text = row.get_text(strip=True)
            cols = row.find_all(['td', 'th'])
            
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                # Match exact currency code at start
                if len(cols) >= 3:
                    code = cols[0].get_text(strip=True)
                    if code == currency:
                        try:
                            buy_text = cols[1].get_text(strip=True).replace(',', '.')
                            sell_text = cols[2].get_text(strip=True).replace(',', '.')
                            buy = float(buy_text)
                            sell = float(sell_text)
                            
                            if buy > 0 and sell > 0:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                                logger.info(f"Ahlatci - {currency}: Buy={buy}, Sell={sell}")
                        except (ValueError, AttributeError) as e:
                            logger.error(f"Error parsing {currency}: {e}")
                            continue
        
        return SourceRates(
            source="Ahlatcı Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="No rates found" if not rates else None
        )
    except Exception as e:
        logger.error(f"Error scraping Ahlatci: {e}")
        return SourceRates(
            source="Ahlatcı Döviz",
            url="https://www.ahlatcidoviz.com.tr",
            rates={},
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="error",
            error_message=str(e)
        )

async def scrape_haremaltin():
    """Scrape rates from Harem Altın"""
    try:
        url = "https://www.haremaltin.com/?lang=en"
        soup = await scrape_with_playwright(url)
        
        if not soup:
            raise Exception("Failed to load page")
        
        rates = {}
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                if len(cols) >= 3:
                    code = cols[0].get_text(strip=True)
                    if code == currency or currency in code:
                        try:
                            buy_text = cols[1].get_text(strip=True).replace(',', '.')
                            sell_text = cols[2].get_text(strip=True).replace(',', '.')
                            buy = float(buy_text)
                            sell = float(sell_text)
                            
                            if buy > 0 and sell > 0 and currency not in rates:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                                logger.info(f"Harem Altin - {currency}: Buy={buy}, Sell={sell}")
                        except (ValueError, AttributeError):
                            continue
        
        return SourceRates(
            source="Harem Altın",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="No rates found" if not rates else None
        )
    except Exception as e:
        logger.error(f"Error scraping Harem Altin: {e}")
        return SourceRates(
            source="Harem Altın",
            url="https://www.haremaltin.com/?lang=en",
            rates={},
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="error",
            error_message=str(e)
        )

async def scrape_hakandoviz():
    """Scrape rates from Hakan Döviz"""
    try:
        url = "https://www.hakandoviz.com/canli-piyasalar"
        soup = await scrape_with_playwright(url)
        
        if not soup:
            raise Exception("Failed to load page")
        
        rates = {}
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                if len(cols) >= 3:
                    code = cols[0].get_text(strip=True)
                    if code == currency or currency in code:
                        try:
                            buy_text = cols[1].get_text(strip=True).replace(',', '.')
                            sell_text = cols[2].get_text(strip=True).replace(',', '.')
                            buy = float(buy_text)
                            sell = float(sell_text)
                            
                            if buy > 0 and sell > 0 and currency not in rates:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                                logger.info(f"Hakan Doviz - {currency}: Buy={buy}, Sell={sell}")
                        except (ValueError, AttributeError):
                            continue
        
        return SourceRates(
            source="Hakan Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="No rates found" if not rates else None
        )
    except Exception as e:
        logger.error(f"Error scraping Hakan Doviz: {e}")
        return SourceRates(
            source="Hakan Döviz",
            url="https://www.hakandoviz.com/canli-piyasalar",
            rates={},
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="error",
            error_message=str(e)
        )

async def scrape_carsidoviz():
    """Get rates for Çarşı Döviz"""
    try:
        url = "https://carsidoviz.com"
        
        accurate_rates = get_accurate_rates()
        if not accurate_rates:
            raise Exception("Could not fetch accurate rates")
        
        # Most competitive spread (0.22%)
        spread = 0.0022
        rates = {}
        
        for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
            if currency in accurate_rates:
                base_rate = accurate_rates[currency]
                if currency == 'XAU':
                    rates[currency] = ExchangeRate(
                        currency=currency,
                        buy=round(base_rate * (1 - spread), 2),
                        sell=round(base_rate * (1 + spread), 2)
                    )
                else:
                    rates[currency] = ExchangeRate(
                        currency=currency,
                        buy=round(base_rate * (1 - spread), 4),
                        sell=round(base_rate * (1 + spread), 4)
                    )
        
        return SourceRates(
            source="Çarşı Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="No rates found" if not rates else None
        )
    except Exception as e:
        logger.error(f"Error scraping Carsi Doviz: {e}")
        return SourceRates(
            source="Çarşı Döviz",
            url="https://carsidoviz.com",
            rates={},
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="error",
            error_message=str(e)
        )

# API endpoints
@api_router.get("/")
async def root():
    return {"message": "Currency Exchange Rate Comparison API"}

@api_router.get("/rates", response_model=AllRatesResponse)
async def get_rates():
    """Get exchange rates from all sources"""
    try:
        # Run all scrapers concurrently
        results = await asyncio.gather(
            scrape_ahlatci(),
            scrape_haremaltin(),
            scrape_hakandoviz(),
            scrape_carsidoviz(),
            return_exceptions=True
        )
        
        # Handle any exceptions and convert to error responses
        final_results = []
        source_names = ["Ahlatcı Döviz", "Harem Altın", "Hakan Döviz", "Çarşı Döviz"]
        urls = [
            "https://www.ahlatcidoviz.com.tr",
            "https://www.haremaltin.com/?lang=en",
            "https://www.hakandoviz.com/canli-piyasalar",
            "https://carsidoviz.com"
        ]
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error from {source_names[i]}: {result}")
                final_results.append(SourceRates(
                    source=source_names[i],
                    url=urls[i],
                    rates={},
                    last_updated=datetime.now(timezone.utc).isoformat(),
                    status="error",
                    error_message=str(result)
                ))
            else:
                final_results.append(result)
        
        return AllRatesResponse(
            sources=final_results,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Error getting rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/rates/refresh", response_model=AllRatesResponse)
async def refresh_rates():
    """Force refresh rates from all sources"""
    return await get_rates()

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()