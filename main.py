import time
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup, Comment
from openai import OpenAI
from test import *
from constants import OPENAI_API
from parcel_id_extractor import LLMParcelExtractor
from propert_detail_extractor import LLMPropertyExtractor
from scrapper import LLMScrapingStrategy

@dataclass
class ScrapingStep:
    action: str
    description: str
    selector: Optional[str] = None
    text_to_enter: Optional[str] = None
    expected_result: Optional[str] = None
    search_text: Optional[str] = None

@dataclass
class ScrapingResult:
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    next_steps: Optional[List[ScrapingStep]] = None

@dataclass
class SiteConfig:
    url: str
    search_keywords: List[str]
    task_description: str
    purpose: str  # 'source' for first site, 'target' for second site

@dataclass
class TwoSiteScrapingConfig:
    site1: SiteConfig
    site2: SiteConfig
    connection_field: str = "parcel_id"  # Field to transfer between sites


class EnhancedWebScraper:
    def __init__(self, openai_api_key: str, model_name: str = "gpt-4o-mini", headless: bool = False):
        """Initialize scraper with OpenAI API and LLM extractors"""
        self.client = OpenAI(api_key=OPENAI_API)
        self.model_name = model_name
        self.driver = None
        self.max_retries = 3
        self.max_total_steps = 100
        self.search_completed = False  
        self.results_loaded = False   
        
        self.property_extractor = LLMPropertyExtractor(self.client, model_name)
        self.parcel_extractor = LLMParcelExtractor(self.client, model_name)
        self.strategy_generator = LLMScrapingStrategy(self.client, model_name)
        
        self.setup_driver(headless)
    
    def setup_driver(self, headless: bool):
        """Initialize Chrome driver with optimal settings"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
    
    def clean_html(self, html_content: str) -> str:
        """Clean HTML for LLM processing"""
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style", "noscript"]):
            script.decompose()
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        cleaned_html = str(soup)
        cleaned_html = re.sub(r'\s+', ' ', cleaned_html).strip()
        cleaned_html = re.sub(r'>\s+<', '><', cleaned_html)
        return cleaned_html
    
    def find_element_by_text(self, search_text: str, timeout: int = 10):
        """Find element containing specific text"""
        try:
            xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_text.lower()}')]"
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element
        except TimeoutException:
            return None
    
    def wait_for_page_load(self, timeout: int = 10):
        """Wait for page to load after an action"""
        try:
            original_url = self.driver.current_url
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.driver.current_url != original_url:
                    print(f"Page changed to {self.driver.current_url}")
                    break
                time.sleep(0.5)
            time.sleep(3)  
            return True
        except Exception as e:
            print(f"Error waiting for page load: {str(e)}")
            return False

    def check_for_results(self) -> bool:
        """Check if any content is present on the page that might be results"""
        try:
            # Get all visible text content
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.strip()
            
            result_selectors = [
                "table", "tbody tr", "div", "span", "p", 
                "[class*='result']", "[class*='property']", "[class*='data']",
                "[id*='result']", "[id*='property']", "[id*='data']"
            ]
            
            for selector in result_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    for elem in elements:
                        if elem.is_displayed() and elem.text.strip():
                            return True
            
            return len(body_text) > 100
            
        except Exception as e:
            print(f"Error checking for results: {str(e)}")
            return False

    def execute_step(self, step: ScrapingStep) -> ScrapingResult:
        """Execute a single scraping step"""
        try:
            print(f"Executing step: {step.description}")
            
            if step.action == "navigate":
                if step.selector and step.selector.startswith("http"):
                    self.driver.get(step.selector)
                    time.sleep(3)
                    return ScrapingResult(success=True, data={"navigated": True})
                return ScrapingResult(success=False, error="Invalid URL")
            
            elif step.action == "find_input":
                element = self.find_element(step.selector)
                if element and element.is_displayed():
                    return ScrapingResult(success=True, data={"element_found": True})
                return ScrapingResult(success=False, error="Input element not found")
            
            elif step.action == "enter_text":
                element = self.find_element(step.selector)
                if element:
                    element.clear()
                    element.send_keys(step.text_to_enter)
                    return ScrapingResult(success=True, data={"text_entered": step.text_to_enter})
                return ScrapingResult(success=False, error="Input element not found")
            
            elif step.action == "click":
                element = self.find_element(step.selector)
                if element and element.is_enabled():
                    self.driver.execute_script("arguments[0].click();", element)
                    if "search" in step.description.lower() or "submit" in step.description.lower():
                        print("Search action detected - waiting for results...")
                        time.sleep(5)  # Wait for results to load
                        self.search_completed = True
                        self.results_loaded = self.check_for_results()
                        print(f"Results loaded: {self.results_loaded}")
                    time.sleep(2)
                    return ScrapingResult(success=True, data={"clicked": True})
                return ScrapingResult(success=False, error="Button not found or not clickable")
            
            elif step.action == "wait":
                wait_time = int(step.text_to_enter) if step.text_to_enter else 5
                time.sleep(wait_time)
                return ScrapingResult(success=True, data={"waited": wait_time})
            
            elif step.action == "wait_for_page_load":
                success = self.wait_for_page_load()
                return ScrapingResult(success=success, data={"page_loaded": success})
            
            elif step.action == "find_by_text":
                element = self.find_element_by_text(step.search_text)
                if element:
                    return ScrapingResult(success=True, data={
                        "element_found": True,
                        "element_text": element.text,
                        "element_tag": element.tag_name
                    })
                return ScrapingResult(success=False, error=f"Element with text '{step.search_text}' not found")
            
            elif step.action == "extract_data":
                selectors_to_try = [
                    step.selector if step.selector else "body",
                    "table", "tbody", "tr", "td", "th",
                    "div", "span", "p", "li", "ul", "ol",
                    "[class*='result']", "[class*='property']", "[class*='data']",
                    "[id*='result']", "[id*='property']", "[id*='data']"
                ]
                
                all_data = []
                for selector in selectors_to_try:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed() and elem.text.strip():
                                all_data.append({
                                    "text": elem.text.strip(), 
                                    "html": elem.get_attribute("outerHTML")[:5000], 
                                    "selector": selector,
                                    "tag": elem.tag_name
                                })
                    except Exception as e:
                        print(f"Error with selector {selector}: {e}")
                        continue
                
                unique_data = []
                seen_texts = set()
                for item in all_data:
                    text = item["text"]
                    if (text not in seen_texts and 
                        len(text) > 5 and 
                        not text.isspace() and
                        len(text.split()) > 1):  
                        unique_data.append(item)
                        seen_texts.add(text)
                
                if unique_data:
                    print(f"Extracted {len(unique_data)} unique data items")
                    return ScrapingResult(success=True, data={"extracted_data": unique_data})
                
                return ScrapingResult(success=False, error="No meaningful data elements found")
            
        except Exception as e:
            return ScrapingResult(success=False, error=f"Execution error: {str(e)}")
    
    def find_element(self, selector: str, timeout: int = 10):
        """Find element with improved error handling"""
        try:
            if selector.startswith("//"):
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
            else:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            return element
        except TimeoutException:
            return None
    
    def scrape_single_site(self, site_config: SiteConfig) -> Dict:
        """Scrape a single site with LLM guidance"""
        total_steps = 0
        failed_attempts = []
        
        self.search_completed = False
        self.results_loaded = False
        
        print(f"Starting scraping on: {site_config.url}")
        self.driver.get(site_config.url)
        time.sleep(3)
        
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while total_steps < self.max_total_steps:
            html_content = self.driver.page_source
            cleaned_html = self.clean_html(html_content)
            
            if self.search_completed and not self.results_loaded:
                self.results_loaded = self.check_for_results()
                print(f"Results check after search: {self.results_loaded}")
            
            llm_response = self.strategy_generator.get_scraping_strategy(
                cleaned_html, 
                site_config.task_description, 
                site_config.search_keywords, 
                failed_attempts[-3:], 
                self.search_completed
            )
            
            if "error" in llm_response:
                return {"success": False, "error": llm_response["error"]}
            
            steps = llm_response.get("steps", [])
            step_results = []
            
            for step_data in steps:
                if total_steps >= self.max_total_steps:
                    break
                
                step = ScrapingStep(
                    action=step_data["action"],
                    description=step_data["description"],
                    selector=step_data.get("selector"),
                    text_to_enter=step_data.get("text_to_enter"),
                    expected_result=step_data.get("expected_result"),
                    search_text=step_data.get("search_text")
                )
                
                if step.action == "enter_text" and site_config.search_keywords and not step.text_to_enter:
                    step.text_to_enter = site_config.search_keywords[0]
                
                print(f"Step {total_steps + 1}: {step.description}")
                result = self.execute_step(step)
                step_results.append(result)
                total_steps += 1
                
                if not result.success:
                    failed_attempts.append(f"Step: {step.description}, Error: {result.error}")
                    print(f"Step failed: {result.error}")
                    consecutive_failures += 1
                    break
                else:
                    print(f"Step succeeded: {step.description}")
                    consecutive_failures = 0
                
                if step.action == "extract_data" and result.success:
                    extracted_data = result.data.get("extracted_data", [])
                    if extracted_data:
                        return {
                            "success": True,
                            "data": result.data,
                            "total_steps": total_steps,
                            "final_url": self.driver.current_url,
                            "site_config": site_config
                        }
            
            if self.search_completed and self.results_loaded:
                print("Attempting direct data extraction...")
                extract_step = ScrapingStep(
                    action="extract_data",
                    description="Extract all available data from current page",
                    selector="body"
                )
                result = self.execute_step(extract_step)
                if result.success and result.data.get("extracted_data"):
                    return {
                        "success": True,
                        "data": result.data,
                        "total_steps": total_steps,
                        "final_url": self.driver.current_url,
                        "site_config": site_config
                    }
            
            if consecutive_failures >= max_consecutive_failures:
                print(f"Too many consecutive failures ({consecutive_failures}), stopping")
                break
            
            if not any(r.success for r in step_results):
                if len(failed_attempts) >= self.max_retries:
                    break
                print("All steps failed, retrying with different approach...")
                continue
            
            time.sleep(2)
        
        return {
            "success": False,
            "error": "Maximum attempts reached without successful completion",
            "failed_attempts": failed_attempts,
            "total_steps": total_steps,
            "site_config": site_config
        }
    
    def scrape_sites(self, config: TwoSiteScrapingConfig) -> Dict:
        """
        Main function to scrape two websites with data transfer
        """
        print("=== Starting Two-Site Scraping with LLM Processing ===")
        
        print(f"\n--- Step 1: Scraping {config.site1.url} ---")
        site1_result = self.scrape_single_site(config.site1)
        
        if not site1_result.get("success"):
            return {
                "success": False,
                "error": "Failed to scrape first site",
                "site1_result": site1_result
            }
        
        site1_raw_data = site1_result.get("data", {}).get("extracted_data", [])
        site1_property_details = self.property_extractor.extract_property_details(
            site1_raw_data, config.site1.purpose
        )
        
        parcel_ids = self.parcel_extractor.extract_parcel_ids(site1_raw_data)
        
        if not parcel_ids:
            return {
                "success": False,
                "error": "No parcel IDs found in first site data",
                "site1_property_details": site1_property_details,
                "site1_raw_data": site1_raw_data
            }
        
        print(f"Found parcel IDs: {parcel_ids}")
        
        print(f"\n--- Step 2: Searching {config.site2.url} with parcel ID: {parcel_ids[0]} ---")
        
        site2_config_updated = SiteConfig(
            url=config.site2.url,
            search_keywords=[parcel_ids[0]],  # Use the first found parcel ID
            task_description=config.site2.task_description,
            purpose=config.site2.purpose
        )
        
        site2_result = self.scrape_single_site(site2_config_updated)
        
        site2_property_details = {"error": "Site 2 scraping failed"}
        if site2_result.get("success"):
            site2_raw_data = site2_result.get("data", {}).get("extracted_data", [])
            site2_property_details = self.property_extractor.extract_property_details(
                site2_raw_data, config.site2.purpose
            )
        
        return {
            "success": site2_result.get("success", False),
            "scraping_summary": {
                "site1_url": config.site1.url,
                "site2_url": config.site2.url,
                "parcel_ids_found": parcel_ids,
                "used_parcel_id": parcel_ids[0] if parcel_ids else None,
                "connection_field": config.connection_field
            },
            "site1_property_details": site1_property_details,
            "site2_property_details": site2_property_details
        }
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def main():
        
    scraper = EnhancedWebScraper(
        openai_api_key=OPENAI_API,
        model_name="gpt-4o-mini", 
        headless=False
    )
    
    site1_config = SiteConfig(
        url=TEST_URL1,
        search_keywords=INPUT_KEYWORD,  # Your search terms
        task_description="Search for property information and extract all available details including parcel identifiers",
        purpose="source"
    )
    
    site2_config = SiteConfig(
        url=TEST_URL2,
        search_keywords=[],  # Will be filled with parcel ID from site1
        task_description="Search using the parcel ID and extract detailed tax and property information",
        purpose="target"
    )
    
    config = TwoSiteScrapingConfig(
        site1=site1_config,
        site2=site2_config,
        connection_field="parcel_id"
    )
    
    try:
        result = scraper.scrape_sites(config)
        print("\n=== FINAL STRUCTURED RESULT ===")
        print(json.dumps(result, indent=2, default=str))
    finally:
        scraper.close()

if __name__ == "__main__":
    main()