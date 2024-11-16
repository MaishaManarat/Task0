import openai
import os
from dotenv import load_dotenv
from agent.CVE import CVE
import asyncio
from playwright.async_api import async_playwright
from langchain.llms import OpenAI

async def main():
    load_dotenv()
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    openai.api_key = OPENAI_API_KEY
    
    print("\nPlease enter a URL for me to hack")
    await asyncio.sleep(0.5)

    url = input('\nURL: ')

    # Initialize the LangChain LLM model
    llm_model = OpenAI(temperature=0.7)

    # Ask for CVE ID here
    cve_id = input("Enter the CVE ID to exploit: ").strip()
    
    async with async_playwright() as playwright:
        # Pass the cve_id argument during instantiation
        cve: CVE = CVE(base_url=url, llm_model=llm_model, cve_id=cve_id)
        await cve.startup(playwright)  # Start the playwright and page instance

        # Run the exploitation
        success = await cve.trial()
        print("Exploitation successful:", success)

        # Optionally close the browser properly
        await cve.shutDown()

if __name__ == '__main__':
    asyncio.run(main())
