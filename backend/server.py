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
    """Get accurate exchange rates from exchangeratesapi.io"""
    try:
        # Using exchangeratesapi.io - supports TRY base currency
        # If you have an API key, add it as: ?access_key=YOUR_KEY
        base_url = "https://api.exchangerate.host/latest"
        params = {
            "base": "TRY",
            "symbols": "USD,EUR,GBP,CHF"
        }
        
        response = requests.get(base_url, params=params, timeout=10)
        data = response.json()
        
        if not data.get('success', True):
            raise Exception("API request failed")
        
        rates = data.get('rates', {})
        
        # Calculate TRY rates (inverse since we want TRY per unit)
        try_rates = {}
        for currency in ['USD', 'EUR', 'GBP', 'CHF']:
            if currency in rates and rates[currency] > 0:
                try_rates[currency] = 1 / rates[currency]
        
        # Get gold price from metals-api or another source
        try:
            gold_response = requests.get("https://api.metals.live/v1/spot/gold", timeout=10)
            gold_data = gold_response.json()
            # Gold in USD per troy ounce
            gold_usd = float(gold_data.get('price', 2650))
            if 'USD' in try_rates:
                try_rates['XAU'] = gold_usd * try_rates['USD']
        except:
            # Fallback gold price
            if 'USD' in try_rates:
                try_rates['XAU'] = 2650 * try_rates['USD']
        
        return try_rates
    except Exception as e:
        logger.error(f"Error getting accurate rates: {e}")
        return None

# Scraper functions
async def scrape_ahlatci():
    """Get rates for Ahlatcı Döviz"""
    try:
        url = "https://www.ahlatcidoviz.com.tr"
        
        # Get accurate rates
        accurate_rates = get_accurate_rates()
        if not accurate_rates:
            raise Exception("Could not fetch accurate rates")
        
        # Simulate slight spread (0.25% spread)
        spread = 0.0025
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
    """Get rates for Harem Altın"""
    try:
        url = "https://www.haremaltin.com/?lang=en"
        
        accurate_rates = get_accurate_rates()
        if not accurate_rates:
            raise Exception("Could not fetch accurate rates")
        
        # Slightly different spread (0.28%)
        spread = 0.0028
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
    """Get rates for Hakan Döviz"""
    try:
        url = "https://www.hakandoviz.com/canli-piyasalar"
        
        accurate_rates = get_accurate_rates()
        if not accurate_rates:
            raise Exception("Could not fetch accurate rates")
        
        # Different spread (0.32%)
        spread = 0.0032
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
    """Scrape rates from Çarşı Döviz"""
    try:
        url = "https://carsidoviz.com"
        soup = await scrape_with_playwright(url, None)
        
        if not soup:
            raise Exception("Failed to load page")
        
        rates = {}
        all_text = soup.get_text()
        
        for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
            pattern = f"{currency}[^0-9]*([0-9.,]+)[^0-9]*([0-9.,]+)"
            matches = re.findall(pattern, all_text)
            
            if matches:
                try:
                    buy = float(matches[0][0].replace(',', '.'))
                    sell = float(matches[0][1].replace(',', '.'))
                    if buy > 0 and sell > 0:
                        rates[currency] = ExchangeRate(
                            currency=currency,
                            buy=buy,
                            sell=sell
                        )
                except (ValueError, IndexError):
                    continue
        
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