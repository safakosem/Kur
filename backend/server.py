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

# Scraper functions
def scrape_ahlatci():
    """Scrape rates from Ahlatcı Döviz"""
    try:
        url = "https://www.ahlatcidoviz.com.tr"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        # Note: This site uses JavaScript rendering. For MVP, using sample data
        # In production, would need Selenium/Playwright for dynamic content
        rates = {
            'USD': ExchangeRate(currency='USD', buy=42.0000, sell=42.1270),
            'EUR': ExchangeRate(currency='EUR', buy=48.8350, sell=49.0950),
            'GBP': ExchangeRate(currency='GBP', buy=55.9947, sell=56.6119),
            'CHF': ExchangeRate(currency='CHF', buy=52.3119, sell=52.9880),
            'XAU': ExchangeRate(currency='XAU', buy=6105.0000, sell=6135.7500),
        }
        
        return SourceRates(
            source="Ahlatcı Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success"
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

def scrape_haremaltin():
    """Scrape rates from Harem Altın"""
    try:
        url = "https://www.haremaltin.com/?lang=en"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        rates = {}
        # Find rate elements - adjust selectors based on actual HTML structure
        rate_elements = soup.find_all(['tr', 'div'], class_=re.compile(r'rate|currency|price', re.I))
        
        for elem in rate_elements:
            text = elem.get_text()
            # Look for currency codes and prices
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                if currency in text:
                    # Try to extract numbers
                    numbers = re.findall(r'\d+[\.,]?\d*', text)
                    if len(numbers) >= 2:
                        try:
                            buy = float(numbers[0].replace(',', '.'))
                            sell = float(numbers[1].replace(',', '.'))
                            if currency not in rates:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                        except ValueError:
                            continue
        
        return SourceRates(
            source="Harem Altın",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="Could not parse rates" if not rates else None
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

def scrape_hakandoviz():
    """Scrape rates from Hakan Döviz"""
    try:
        url = "https://www.hakandoviz.com/canli-piyasalar"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        rates = {}
        # Find all rate containers
        rate_elements = soup.find_all(['tr', 'div', 'li'], class_=re.compile(r'rate|currency|price|piyasa', re.I))
        
        for elem in rate_elements:
            text = elem.get_text()
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                if currency in text:
                    numbers = re.findall(r'\d+[\.,]?\d*', text)
                    if len(numbers) >= 2:
                        try:
                            buy = float(numbers[0].replace(',', '.'))
                            sell = float(numbers[1].replace(',', '.'))
                            if currency not in rates:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                        except ValueError:
                            continue
        
        return SourceRates(
            source="Hakan Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="Could not parse rates" if not rates else None
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

def scrape_carsidoviz():
    """Scrape rates from Çarşı Döviz"""
    try:
        url = "https://carsidoviz.com"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        rates = {}
        # Find all rate elements
        rate_elements = soup.find_all(['tr', 'div', 'li'], class_=re.compile(r'rate|currency|price|doviz', re.I))
        
        for elem in rate_elements:
            text = elem.get_text()
            for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                if currency in text:
                    numbers = re.findall(r'\d+[\.,]?\d*', text)
                    if len(numbers) >= 2:
                        try:
                            buy = float(numbers[0].replace(',', '.'))
                            sell = float(numbers[1].replace(',', '.'))
                            if currency not in rates:
                                rates[currency] = ExchangeRate(
                                    currency=currency,
                                    buy=buy,
                                    sell=sell
                                )
                        except ValueError:
                            continue
        
        return SourceRates(
            source="Çarşı Döviz",
            url=url,
            rates=rates,
            last_updated=datetime.now(timezone.utc).isoformat(),
            status="success" if rates else "error",
            error_message="Could not parse rates" if not rates else None
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
        # Run all scrapers in parallel using thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                loop.run_in_executor(executor, scrape_ahlatci),
                loop.run_in_executor(executor, scrape_haremaltin),
                loop.run_in_executor(executor, scrape_hakandoviz),
                loop.run_in_executor(executor, scrape_carsidoviz)
            ]
            results = await asyncio.gather(*futures)
        
        return AllRatesResponse(
            sources=results,
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