import os
import asyncio
from dotenv import load_dotenv
from langchain import LLMChain
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from playwright.async_api import async_playwright
from agent.SQLInjector import SQLInjector
from agent.LFI import LFI
from agent.XSS import XSS
from agent.Scanner import Scanner
from agent.Crawler import Crawler
from agent.CVE import CVE
import main_cve

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize LangChain LLM
llm = OpenAI(api_key=OPENAI_API_KEY)


async def enumeration(url, playwright):
    results = []

    ###web technology scan

    scanner: Scanner = Scanner(base_url=url)
    async with async_playwright() as playwright:
        #await scanner.run()
        scanner.run()
        await asyncio.sleep(0.5)
        #await scanner.analyze_headers()
        #await scanner.run_owasp_zap_scan()
        #await scanner.identify_cves()
        #await scanner.generate_summary_report()



    # website crawling  
    crawler: Crawler = Crawler(base_url=url)
    async with async_playwright() as playwright:
        await asyncio.sleep(0.5)
        await crawler.start_crawling()


async def vulnerability_test(url, playwright):
    results = []

    # Define the agents for SQL Injection, XSS, and LFI vulnerabilities
    async def run_injector(agent_class, agent_name):
        async with async_playwright() as playwright:
            agent = agent_class(base_url=url)
            await agent.startup(playwright)
            result = await agent.trial()
            await agent.shutDown()
        return agent_name, result

    # Running SQL Injection test
    sql_injection_result = await run_injector(SQLInjector, "SQL Injection")
    results.append(sql_injection_result)

    # Running XSS test
    xss_result = await run_injector(XSS, "XSS")
    results.append(xss_result)

    # Running LFI test
    lfi_result = await run_injector(LFI, "LFI")
    results.append(lfi_result)

    # Analyze the results and suggest related CVE IDs
    summary_chain = LLMChain(
        llm=llm,
        prompt=PromptTemplate(
            input_variables=["results"],
            template="Analyze the following vulnerability testing results: {results}. "
                     "Summarize what vulnerabilities were found, specify any successful exploits, "
        )
    )

    analysis = summary_chain.run({"results": results})
    print("\n--- Vulnerability Analysis ---\n")
    print(analysis)


async def cve_test(playwright):
        ## CVE Exploit
        print("Now to test CVE exploitation")
        print("\nPlease enter a URL for me to hack")
        await asyncio.sleep(0.5)

        url = input('\nURL: ')


        
        async with async_playwright() as playwright:
            
            cve: CVE = CVE(url=url)
            await cve.startup(playwright)  # Start the playwright and page instance

            # Run the exploitation
            success = await cve.trial()
            print("Exploitation successful:", success)

            # Optionally close the browser properly
            await cve.shutDown()

# Main entry
if __name__ == '__main__':
    url = input("Please enter a URL for vulnerability testing: ")
    
    async def main():
        async with async_playwright() as playwright:
            await enumeration(url, playwright)
            await vulnerability_test(url, playwright)
            await cve_test(playwright)

    asyncio.run(main())
