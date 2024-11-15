import requests
from typing import List, Dict
from utils.spinner import Spinner
from utils.gpt import gpt
import re
import json

class Scanner:
    def __init__(self, base_url: str):
        self.baseURL = base_url
        self.headers_info = {}
        self.detected_software = {}
        self.cve_report = []

    def fetch_http_headers(self):
        """
        Fetch HTTP headers to infer server/software details.
        """
        try:
            with Spinner("Fetching HTTP headers..."):
                response = requests.get(self.baseURL, timeout=10)
                self.headers_info = response.headers
                print(f"HTTP Headers: {self.headers_info}")
        except requests.RequestException as e:
            print(f"Error fetching HTTP headers: {e}")

    def analyze_headers(self):
        """
        Analyze headers to detect software/server details.
        """
        print("Analyzing headers for software details...")
        server_info = self.headers_info.get('Server', '')
        x_powered_by = self.headers_info.get('X-Powered-By', '')
        
        # Detect software, server, and language
        if server_info:
            self.detected_software['Server'] = server_info
        if x_powered_by:
            self.detected_software['Powered-By'] = x_powered_by

        # Example regex for detecting specific versions
        version_regex = r"([\w\-]+)\/([\d\.]+)"
        for key, value in self.headers_info.items():
            match = re.search(version_regex, value)
            if match:
                self.detected_software[match.group(1)] = match.group(2)

        print(f"Detected software: {self.detected_software}")

    def run_owasp_zap_scan(self):
        """
        Use OWASP ZAP to scan the target URL and extract technology information.
        """
        try:
            with Spinner("Running OWASP ZAP scan..."):
                zap_api_url = "http://localhost:8080/JSON/technology/view/technologyList/"
                zap_params = {"baseurl": self.baseURL}
                response = requests.get(zap_api_url, params=zap_params)
                if response.status_code == 200:
                    zap_data = response.json()
                    technologies = zap_data.get("technologyList", [])
                    for tech in technologies:
                        self.detected_software[tech] = "Unknown"
                print(f"Technologies detected by ZAP: {self.detected_software}")
        except Exception as e:
            print(f"Error running OWASP ZAP scan: {e}")


    def query_cves(self, software: str, version: str) -> List[Dict]:
        """
        Use AI (GPT or other models) to find related CVEs for given software and version.
        """
        try:
            # Prompt GPT with contextual information
            prompt = (
                f"I am working on identifying vulnerabilities for the software:\n"
                f"Software: {software}\n"
                f"Version: {version}\n\n"
                f"Please provide a list of possible vulnerabilities (CVE IDs and descriptions) "
                f"related to this software and version. Include vulnerabilities from any known "
                f"databases or references, including potential issues that might be unpatched."
            )
            
            response = gpt(system_msg="", user_msg=prompt)

            # Parse GPT response into a structured format
            cve_matches = re.findall(r'(CVE-\d{4}-\d{4,7}):\s*(.+)', response)
            cves = [{"cve_id": cve[0], "description": cve[1]} for cve in cve_matches]

            print(f"AI Identified CVEs for {software} {version}: {cves}")
            return cves

        except Exception as e:
            print(f"Error querying AI for CVEs: {e}")
            return []

    
    def generate_summary_report(self):
        """
        Generate a detailed report for the scanned website using AI-inferred CVEs.
        Save the CVE details for future reference.
        """
        with Spinner("Generating a detailed report..."):
            # Website Technologies
            software_details = '\n'.join([f"{k}: {v}" for k, v in self.detected_software.items()])
            
            # AI-Queried Vulnerabilities
            cve_details_list = [
                f"CVE ID: {cve['cve_id']}\nCVE Name: {cve['description']}\n"
                for cve in self.cve_report
            ]
            cve_details = '\n'.join(cve_details_list)

            # Construct the report
            report = (
                "---Website Technologies---\n"
                f"{software_details if software_details else 'No technologies detected.'}\n\n"
                "---Potential Vulnerabilities---\n"
                f"{cve_details if cve_details else 'No vulnerabilities found.'}\n"
            )

            # Save the CVE details to a file
            if self.cve_report:
                with open("cve_report.json", "w") as f:
                    json.dump(self.cve_report, f, indent=4)
                print("CVE details saved to 'cve_report.json'.")

            # Print the report
            print(report)

            # Optionally send the report to GPT for summarization
            if cve_details:
                prompt = (
                    f"I scanned a website ({self.baseURL}) and found the following details:\n\n"
                    "---Website Technologies---\n"
                    f"{software_details}\n\n"
                    "---Potential Vulnerabilities---\n"
                )
                response = gpt(system_msg="", user_msg=prompt)
                print("\nGPT-Summarized Report:")
                print(response)


    def run(self):
        """
        Execute the scanner workflow.
        """
        self.fetch_http_headers()
        self.analyze_headers()
        self.run_owasp_zap_scan
        
        for software, version in self.detected_software.items():
            cves = self.query_cves(software, version)
            self.cve_report.extend(cves)

        self.generate_summary_report()
