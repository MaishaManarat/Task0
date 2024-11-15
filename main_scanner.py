import openai
import os
from dotenv import load_dotenv
from agent.Scanner import Scanner
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

    scanner: Scanner = Scanner(base_url=url)
    async with async_playwright() as playwright:
        #await scanner.run()
        scanner.run()
        await asyncio.sleep(0.5)
        #await scanner.analyze_headers()
        #await scanner.run_owasp_zap_scan()
        #await scanner.identify_cves()
        #await scanner.generate_summary_report()

if __name__ == '__main__':
    asyncio.run(main())
