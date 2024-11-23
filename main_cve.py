import openai
import os
from dotenv import load_dotenv
from agent.CVE import CVE
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

    cve: CVE = CVE(url=url)
    async with async_playwright() as playwright:
        await cve.startup(playwright)
        await cve.trial()
        await asyncio.sleep(0.5)
        input('\nClick enter to shut down the browser: ')
        await cve.shutDown()
        

if __name__ == '__main__':
    asyncio.run(main())
