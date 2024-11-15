import openai
import os
from dotenv import load_dotenv
from agent.Crawler import Crawler
import asyncio
from playwright.async_api import async_playwright

async def main():
    
    load_dotenv()
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    openai.api_key = OPENAI_API_KEY
    
    print("\nPlease enter a URL for me to hack")
    await asyncio.sleep(0.5)

    url = input('\nURL: ')
    # url = "http://localhost:3000/"

    crawler: Crawler = Crawler(base_url=url)
    async with async_playwright() as playwright:
        await asyncio.sleep(0.5)
        await crawler.start_crawling()

if __name__ == '__main__':
    asyncio.run(main())
