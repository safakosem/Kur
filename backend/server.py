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

import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Cache for rates
rates_cache = {
    'data': None,
    'last_updated': 0,
    'cache_duration': 5,  # Cache for 5 seconds
    'updating': False  # Flag to prevent multiple simultaneous updates
}

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
            
            if len(cols) >= 3:
                code_text = cols[0].get_text(strip=True).upper()
                
                # Check for regular currencies
                for currency in ['USD', 'EUR', 'GBP', 'CHF']:
                    if code_text == currency or f"{currency}/TRY" in code_text or currency in code_text:
                        try:
                            buy_text = cols[1].get_text(strip=True).replace(',', '.').replace(' ', '')
                            sell_text = cols[2].get_text(strip=True).replace(',', '.').replace(' ', '')
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
                
                # Check for gold - look for "GOLD TRY" (might be repeated like "GOLD TRYGOLD TRY")
                if 'GOLDTRY' in code_text.replace(' ', '') and 'XAU' not in rates:
                    try:
                        buy_text = cols[1].get_text(strip=True).replace(' ', '')
                        sell_text = cols[2].get_text(strip=True).replace(' ', '')
                        
                        # Handle format like "6.070,20" - dot for thousands, comma for decimal
                        # Remove dots (thousands separator) and replace comma with dot
                        buy_text = buy_text.replace('.', '').replace(',', '.')
                        sell_text = sell_text.replace('.', '').replace(',', '.')
                        
                        buy = float(buy_text)
                        sell = float(sell_text)
                        
                        if buy > 100 and sell > 100:  # Sanity check - gold should be > 100
                            rates['XAU'] = ExchangeRate(
                                currency='XAU',
                                buy=buy,
                                sell=sell
                            )
                            logger.info(f"Harem Altin - XAU: Buy={buy}, Sell={sell}")
                    except (ValueError, AttributeError) as e:
                        logger.error(f"Error parsing gold: {e}, buy_text={buy_text}, sell_text={sell_text}")
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
        
        # This site has data in <li> elements like: USD/TRY41,821442,0130
        lis = soup.find_all('li')
        
        for li in lis:
            text = li.get_text(strip=True)
            
            # Look for patterns like USD/TRY41,821442,0130
            for currency in ['USD/TRY', 'EUR/TRY', 'GBP/TRY', 'CHF/TRY']:
                if currency in text:
                    # Extract the numbers after the currency code
                    remaining = text.replace(currency, '')
                    # Split by comma to get buy and sell
                    parts = remaining.split(',')
                    
                    if len(parts) >= 2:
                        try:
                            # Reconstruct the numbers with decimal points
                            buy_str = parts[0] + '.' + parts[1][:4] if len(parts[1]) >= 4 else parts[0]
                            
                            # Find sell price (next number group)
                            if len(parts[1]) > 4:
                                sell_part1 = parts[1][4:]
                                sell_str = sell_part1
                                if len(parts) > 2:
                                    sell_str = sell_part1 + '.' + parts[2][:4]
                            else:
                                sell_str = parts[1] if len(parts) > 1 else buy_str
                            
                            buy = float(buy_str.replace(',', '.'))
                            sell = float(sell_str.replace(',', '.'))
                            
                            curr_code = currency.split('/')[0]  # Get USD, EUR, etc.
                            
                            if buy > 0 and sell > 0 and curr_code not in rates:
                                rates[curr_code] = ExchangeRate(
                                    currency=curr_code,
                                    buy=buy,
                                    sell=sell
                                )
                                logger.info(f"Hakan Doviz - {curr_code}: Buy={buy}, Sell={sell}")
                        except (ValueError, AttributeError, IndexError) as e:
                            logger.error(f"Error parsing {currency} from Hakan: {e}, text: {text}")
                            continue
            
            # Look for XAU (gold) - format: HAS/TRY6.090,006.141,00
            if 'HAS/TRY' in text and 'XAU' not in rates:
                try:
                    # Extract numbers after HAS/TRY
                    remaining = text.replace('HAS/TRY', '')
                    # Split by comma - format is like 6.090,006.141,00
                    parts = remaining.split(',')
                    
                    if len(parts) >= 3:
                        # Format: 6.090,006.141,00 -> buy: 6090.00, sell: 6141.00
                        buy_str = parts[0].replace('.', '') + '.' + parts[1][:2]
                        sell_str = parts[1][2:].replace('.', '') + '.' + parts[2][:2]
                        
                        buy = float(buy_str)
                        sell = float(sell_str)
                        
                        if buy > 100 and sell > 100:  # Sanity check
                            rates['XAU'] = ExchangeRate(
                                currency='XAU',
                                buy=buy,
                                sell=sell
                            )
                            logger.info(f"Hakan Doviz - XAU: Buy={buy}, Sell={sell}")
                except Exception as e:
                    logger.error(f"Error parsing gold from Hakan: {e}, text: {text}")
        
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
        soup = await scrape_with_playwright(url)
        
        if not soup:
            raise Exception("Failed to load page")
        
        rates = {}
        
        # This site might use Turkish names like DOLAR, EURO, etc.
        currency_mapping = {
            'DOLAR': 'USD',
            'USD': 'USD',
            'EURO': 'EUR',
            'EUR': 'EUR',
            'STERLİN': 'GBP',
            'STERLIN': 'GBP',
            'GBP': 'GBP',
            'İSVİÇRE FRANGI': 'CHF',
            'CHF': 'CHF',
            'ALTIN': 'XAU',
            'XAU': 'XAU'
        }
        
        # Strategy 1: Look in table rows
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all(['td', 'th'])
            
            if len(cols) >= 3:
                code = cols[0].get_text(strip=True).upper()
                
                # Check if this row is for a currency we want
                mapped_currency = None
                for turkish_name, english_code in currency_mapping.items():
                    if turkish_name in code:
                        mapped_currency = english_code
                        break
                
                if mapped_currency and mapped_currency not in rates:
                    try:
                        buy_text = cols[1].get_text(strip=True).replace(',', '.').replace(' ', '')
                        sell_text = cols[2].get_text(strip=True).replace(',', '.').replace(' ', '')
                        buy = float(buy_text)
                        sell = float(sell_text)
                        
                        if buy > 0 and sell > 0:
                            rates[mapped_currency] = ExchangeRate(
                                currency=mapped_currency,
                                buy=buy,
                                sell=sell
                            )
                            logger.info(f"Carsi Doviz - {mapped_currency}: Buy={buy}, Sell={sell}")
                    except (ValueError, AttributeError) as e:
                        logger.error(f"Error parsing {code}: {e}")
                        continue
        
        # Strategy 2: Look in divs
        if not rates:
            all_divs = soup.find_all(['div', 'span', 'p'])
            for div in all_divs:
                text = div.get_text(strip=True).upper()
                
                for turkish_name, english_code in currency_mapping.items():
                    if turkish_name in text and english_code not in rates:
                        # Try to find numbers in the parent or nearby elements
                        parent = div.parent
                        if parent:
                            parent_text = parent.get_text(strip=True)
                            import re
                            numbers = re.findall(r'(\d{2}[.,]\d{4})', parent_text)
                            if len(numbers) >= 2:
                                try:
                                    buy = float(numbers[0].replace(',', '.'))
                                    sell = float(numbers[1].replace(',', '.'))
                                    if buy > 0 and sell > 0:
                                        rates[english_code] = ExchangeRate(
                                            currency=english_code,
                                            buy=buy,
                                            sell=sell
                                        )
                                        logger.info(f"Carsi Doviz - {english_code}: Buy={buy}, Sell={sell}")
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
    """Get exchange rates from all sources (with caching)"""
    try:
        current_time = time.time()
        
        # If cache exists and is valid, return it immediately
        if rates_cache['data'] and (current_time - rates_cache['last_updated']) < rates_cache['cache_duration']:
            logger.info("Returning cached rates")
            return rates_cache['data']
        
        # If cache is expired but an update is in progress, return stale cache
        if rates_cache['updating'] and rates_cache['data']:
            logger.info("Update in progress, returning stale cache")
            return rates_cache['data']
        
        # Mark as updating
        rates_cache['updating'] = True
        
        try:
            # Cache expired or doesn't exist, fetch new rates
            logger.info("Fetching fresh rates from websites")
            
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
            
            response = AllRatesResponse(
                sources=final_results,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            # Update cache
            rates_cache['data'] = response
            rates_cache['last_updated'] = current_time
            
            return response
            
        finally:
            # Always clear the updating flag
            rates_cache['updating'] = False
        
    except Exception as e:
        logger.error(f"Error getting rates: {e}")
        rates_cache['updating'] = False
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