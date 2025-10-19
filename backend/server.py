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
            
            # Look for XAU (gold) - format might be HAS/TRY or XAU/USD
            if 'HAS/TRY' in text or 'XAU' in text:
                try:
                    # Try to extract numbers
                    import re
                    numbers = re.findall(r'(\d+\.?\d*),(\d+)', text)
                    if len(numbers) >= 1:
                        buy = float(numbers[0][0] + numbers[0][1][:3])
                        if len(numbers) >= 2:
                            sell = float(numbers[1][0] + numbers[1][1][:3])
                        else:
                            sell = buy * 1.01
                        
                        if 'XAU' not in rates and buy > 100:
                            rates['XAU'] = ExchangeRate(
                                currency='XAU',
                                buy=buy,
                                sell=sell
                            )
                            logger.info(f"Hakan Doviz - XAU: Buy={buy}, Sell={sell}")
                except Exception as e:
                    logger.error(f"Error parsing gold from Hakan: {e}")
        
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
        
        # Try multiple strategies to find rates
        # Strategy 1: Look in table rows
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
                                logger.info(f"Carsi Doviz - {currency}: Buy={buy}, Sell={sell}")
                        except (ValueError, AttributeError):
                            continue
        
        # Strategy 2: Look for <li> elements like Hakan Döviz
        if not rates:
            lis = soup.find_all('li')
            for li in lis:
                text = li.get_text(strip=True)
                
                for currency in ['USD/TRY', 'EUR/TRY', 'GBP/TRY', 'CHF/TRY']:
                    if currency in text:
                        remaining = text.replace(currency, '')
                        parts = remaining.split(',')
                        
                        if len(parts) >= 2:
                            try:
                                buy_str = parts[0] + '.' + parts[1][:4] if len(parts[1]) >= 4 else parts[0]
                                
                                if len(parts[1]) > 4:
                                    sell_part1 = parts[1][4:]
                                    sell_str = sell_part1
                                    if len(parts) > 2:
                                        sell_str = sell_part1 + '.' + parts[2][:4]
                                else:
                                    sell_str = parts[1] if len(parts) > 1 else buy_str
                                
                                buy = float(buy_str.replace(',', '.'))
                                sell = float(sell_str.replace(',', '.'))
                                
                                curr_code = currency.split('/')[0]
                                
                                if buy > 0 and sell > 0 and curr_code not in rates:
                                    rates[curr_code] = ExchangeRate(
                                        currency=curr_code,
                                        buy=buy,
                                        sell=sell
                                    )
                                    logger.info(f"Carsi Doviz - {curr_code}: Buy={buy}, Sell={sell}")
                            except (ValueError, AttributeError, IndexError):
                                continue
        
        # Strategy 3: Look in divs with class containing 'price' or 'currency'
        if not rates:
            all_divs = soup.find_all('div')
            for div in all_divs:
                text = div.get_text(strip=True)
                for currency in ['USD', 'EUR', 'GBP', 'CHF', 'XAU']:
                    if currency in text:
                        # Try to extract numbers nearby
                        import re
                        numbers = re.findall(r'\d+[.,]\d+', text)
                        if len(numbers) >= 2:
                            try:
                                buy = float(numbers[0].replace(',', '.'))
                                sell = float(numbers[1].replace(',', '.'))
                                if buy > 0 and sell > 0 and currency not in rates:
                                    rates[currency] = ExchangeRate(
                                        currency=currency,
                                        buy=buy,
                                        sell=sell
                                    )
                                    logger.info(f"Carsi Doviz - {currency}: Buy={buy}, Sell={sell}")
                                    break
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