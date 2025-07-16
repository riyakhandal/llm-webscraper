import time
import json
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import boto3
import json as json_module
from urllib.parse import urljoin, urlparse
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
class WebsiteResult:
    url: str
    website_name: str
    success: bool
    extracted_data: Optional[Dict] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    steps_taken: Optional[int] = None

class EnhancedWebScraper:
    def __init__(self, bedrock_client=None, model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", 
                 aws_region="us-west-2", headless: bool = True):
        """
        Initialize enhanced scraper with AWS Bedrock for CSV-driven scraping
        """
        if bedrock_client:
            self.bedrock_client = bedrock_client
        else:
            self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        
        self.model_id = model_id
        self.driver = None
        self.max_retries = 5
        self.max_total_steps = 50
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
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
        self.driver.set_page_load_timeout(30)
    
    def clean_html(self, html_content: str) -> str:
        """Clean HTML for LLM processing while preserving structure"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for script in soup(["script", "style", "noscript", "meta", "link"]):
            script.decompose()
        
        # Remove comments
        from bs4 import Comment
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        
        # Get cleaned HTML
        cleaned_html = str(soup)
        
        # Remove excessive whitespace but preserve structure
        import re
        cleaned_html = re.sub(r'\n\s*\n', '\n', cleaned_html)
        cleaned_html = re.sub(r'\s+', ' ', cleaned_html)
        
        # Limit size for LLM processing
        if len(cleaned_html) > 20000:
            cleaned_html = cleaned_html[:20000] + "... [truncated]"
        
        return cleaned_html.strip()
    
    def get_llm_analysis(self, html_content: str, task_description: str, 
                        website_context: str = "", keywords: List[str] = None,
                        previous_attempts: List[str] = None) -> Dict:
        """Enhanced LLM analysis with better context understanding"""
        
        failed_attempts_context = ""
        if previous_attempts:
            failed_attempts_context = f"\n\nPrevious failed attempts:\n" + "\n".join(previous_attempts[-3:])
        
        keywords_context = ""
        if keywords:
            keywords_context = f"\n\nKeywords to search for: {', '.join(keywords)}"
        
        prompt = f"""
        You are an expert web scraping AI assistant. Your task is to analyze HTML content and provide intelligent scraping instructions.

        WEBSITE CONTEXT: {website_context}
        TASK: {task_description}
        {keywords_context}
        
        HTML CONTENT:
        {html_content}
        
        {failed_attempts_context}
        
        INSTRUCTIONS:
        1. Analyze the HTML structure intelligently
        2. Look for forms, input fields, buttons, search functionality
        3. Identify data containers, tables, lists, or result sections
        4. If this is a search/form page, provide steps to fill and submit forms
        5. If this is a results page, provide steps to extract meaningful data
        6. Be adaptive - different websites have different structures
        7. Focus on extracting useful, structured information
        8. Look for patterns that suggest valuable data (tables, lists, cards, etc.)
        
        IMPORTANT: Your goal is to find and extract ANY useful information from the website. This could be:
        - Search results
        - Product listings
        - Contact information
        - News articles
        - Data tables
        - Directory listings
        - Any structured information that might be valuable
        
        Respond with a JSON object:
        {{
            "analysis": "Your understanding of what this page contains and what can be extracted",
            "strategy": "Your approach to extract useful information",
            "steps": [
                {{
                    "action": "navigate|find_input|enter_text|click|wait|extract_data|find_by_text|scroll|wait_for_load",
                    "description": "Clear description of what this step does",
                    "selector": "CSS selector or XPath",
                    "text_to_enter": "Text to enter (if applicable)",
                    "expected_result": "What should happen after this step",
                    "search_text": "Text to search for (if applicable)"
                }}
            ],
            "data_extraction_selectors": [
                "CSS selectors for extracting meaningful data from the page"
            ],
            "confidence": "high|medium|low",
            "page_type": "form|results|content|directory|other"
        }}
        
        Guidelines:
        - Prefer CSS selectors over XPath
        - Be specific but flexible with selectors
        - Consider common web patterns (forms, search boxes, result containers)
        - Always include data extraction steps
        - Adapt to the specific website structure you see
        - If you see a form, provide steps to fill and submit it
        - If you see data already, provide steps to extract it
        """
        
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "temperature": 0.3,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json_module.dumps(body),
                contentType='application/json'
            )
            
            response_body = json_module.loads(response['body'].read().decode('utf-8'))
            content = response_body['content'][0]['text']
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json_module.loads(json_match.group())
            else:
                return {"error": "Failed to parse LLM response", "raw_response": content}
                
        except Exception as e:
            logger.error(f"Bedrock API error: {str(e)}")
            return {"error": f"Bedrock API error: {str(e)}"}
    
    def execute_step(self, step: ScrapingStep) -> ScrapingResult:
        """Execute scraping step with enhanced error handling"""
        try:
            logger.info(f"Executing step: {step.action} - {step.description}")
            
            if step.action == "navigate":
                if step.selector and step.selector.startswith("http"):
                    self.driver.get(step.selector)
                    time.sleep(3)
                    return ScrapingResult(success=True, data={"navigated": True})
                else:
                    return ScrapingResult(success=False, error="Invalid URL for navigation")
            
            elif step.action == "find_input":
                element = self.find_element(step.selector)
                if element and element.is_displayed():
                    return ScrapingResult(success=True, data={"element_found": True})
                else:
                    return ScrapingResult(success=False, error="Input element not found or not visible")
            
            elif step.action == "enter_text":
                element = self.find_element(step.selector)
                if element:
                    element.clear()
                    element.send_keys(step.text_to_enter or "")
                    return ScrapingResult(success=True, data={"text_entered": step.text_to_enter})
                else:
                    return ScrapingResult(success=False, error="Input element not found")
            
            elif step.action == "click":
                element = self.find_element(step.selector)
                if element:
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(2)
                    return ScrapingResult(success=True, data={"clicked": True})
                else:
                    return ScrapingResult(success=False, error="Clickable element not found")
            
            elif step.action == "wait" or step.action == "wait_for_load":
                wait_time = 3
                if step.text_to_enter:
                    try:
                        wait_time = int(step.text_to_enter)
                    except:
                        wait_time = 3
                time.sleep(wait_time)
                return ScrapingResult(success=True, data={"waited": wait_time})
            
            elif step.action == "scroll":
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                return ScrapingResult(success=True, data={"scrolled": True})
            
            elif step.action == "find_by_text":
                element = self.find_element_by_text(step.search_text or step.text_to_enter)
                if element:
                    return ScrapingResult(success=True, data={
                        "element_found": True,
                        "element_text": element.text,
                        "element_tag": element.tag_name
                    })
                else:
                    return ScrapingResult(success=False, error=f"Element with text not found")
            
            elif step.action == "extract_data":
                return self.extract_data_intelligently(step.selector)
            
            else:
                return ScrapingResult(success=False, error=f"Unknown action: {step.action}")
                
        except Exception as e:
            logger.error(f"Error executing step: {str(e)}")
            return ScrapingResult(success=False, error=f"Execution error: {str(e)}")
    
    def extract_data_intelligently(self, selector: str = None) -> ScrapingResult:
        """Use LLM to intelligently extract data from the current page"""
        try:
            html_content = self.driver.page_source
            cleaned_html = self.clean_html(html_content)
            
            # Ask LLM to analyze and extract data
            extraction_prompt = f"""
            Analyze this HTML content and extract ALL useful structured information.
            
            HTML CONTENT:
            {cleaned_html}
            
            Extract information and return as JSON with this structure:
            {{
                "extracted_data": {{
                    "main_content": "Primary content/data found",
                    "structured_data": [
                        {{
                            "type": "table|list|card|form|text",
                            "title": "Section title or description",
                            "content": "The actual data content",
                            "details": {{
                                "key1": "value1",
                                "key2": "value2"
                            }}
                        }}
                    ],
                    "metadata": {{
                        "page_title": "Page title",
                        "total_items": "Number of items found",
                        "categories": ["category1", "category2"]
                    }}
                }},
                "confidence": "high|medium|low",
                "data_quality": "excellent|good|fair|poor"
            }}
            
            Focus on extracting:
            - Tables and their data
            - Lists and their items
            - Forms and their fields
            - Product/service information
            - Contact details
            - Any structured information that could be valuable
            
            Be thorough but organized in your extraction.
            """
            
            try:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "user",
                            "content": extraction_prompt
                        }
                    ]
                }
                
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json_module.dumps(body),
                    contentType='application/json'
                )
                
                response_body = json_module.loads(response['body'].read().decode('utf-8'))
                content = response_body['content'][0]['text']
                
                # Extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    extracted_data = json_module.loads(json_match.group())
                    return ScrapingResult(success=True, data=extracted_data)
                else:
                    return ScrapingResult(success=False, error="Failed to parse extraction response")
                    
            except Exception as e:
                logger.error(f"Data extraction error: {str(e)}")
                return ScrapingResult(success=False, error=f"Data extraction error: {str(e)}")
                
        except Exception as e:
            return ScrapingResult(success=False, error=f"Extraction error: {str(e)}")
    
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
    
    def scrape_website_intelligently(self, url: str, website_name: str = "", 
                                   keywords: List[str] = None) -> WebsiteResult:
        """Scrape a single website with full LLM intelligence"""
        
        start_time = time.time()
        logger.info(f"Starting intelligent scraping of: {website_name} ({url})")
        
        try:
            # Navigate to website
            self.driver.get(url)
            time.sleep(3)
            
            total_steps = 0
            failed_attempts = []
            
            # Enhanced task description
            task_description = f"""
            Intelligently analyze and extract useful information from this website: {website_name}
            
            Your objectives:
            1. Understand what type of website this is
            2. Look for forms, search functionality, or interactive elements
            3. If there are search forms, use the provided keywords to search
            4. Extract ANY useful structured information you find
            5. Be adaptive - every website is different
            6. Focus on finding valuable data that could be useful
            
            Keywords available: {keywords if keywords else 'None provided'}
            
            Remember: Your goal is to find and extract useful information, whether that's through:
            - Searching with keywords
            - Browsing available data
            - Extracting directory listings
            - Finding contact information
            - Collecting product/service information
            - Or any other valuable structured data
            """
            
            # Main scraping loop
            while total_steps < self.max_total_steps:
                html_content = self.driver.page_source
                cleaned_html = self.clean_html(html_content)
                
                # Get LLM analysis
                llm_response = self.get_llm_analysis(
                    cleaned_html, 
                    task_description, 
                    website_name,
                    keywords,
                    failed_attempts[-3:]
                )
                
                if "error" in llm_response:
                    logger.error(f"LLM analysis error: {llm_response['error']}")
                    break
                
                logger.info(f"LLM Analysis: {llm_response.get('analysis', 'No analysis provided')}")
                logger.info(f"LLM Strategy: {llm_response.get('strategy', 'No strategy provided')}")
                
                # Execute LLM-suggested steps
                steps = llm_response.get("steps", [])
                step_results = []
                
                for step_data in steps:
                    if total_steps >= self.max_total_steps:
                        break
                    
                    step = ScrapingStep(
                        action=step_data.get("action", ""),
                        description=step_data.get("description", ""),
                        selector=step_data.get("selector"),
                        text_to_enter=step_data.get("text_to_enter"),
                        expected_result=step_data.get("expected_result"),
                        search_text=step_data.get("search_text")
                    )
                    
                    # Enhanced keyword handling
                    if step.action == "enter_text" and keywords:
                        if not step.text_to_enter or step.text_to_enter in ["[KEYWORD]", "[SEARCH_TERM]"]:
                            step.text_to_enter = keywords[0]
                        elif "[KEYWORD]" in step.text_to_enter:
                            step.text_to_enter = step.text_to_enter.replace("[KEYWORD]", keywords[0])
                    
                    result = self.execute_step(step)
                    step_results.append(result)
                    total_steps += 1
                    
                    if not result.success:
                        failed_attempts.append(f"Step: {step.description}, Error: {result.error}")
                        logger.warning(f"Step failed: {result.error}")
                        break
                    
                    # Check if we got useful data
                    if result.data and "extracted_data" in result.data:
                        processing_time = time.time() - start_time
                        logger.info(f"Successfully extracted data from {website_name}")
                        return WebsiteResult(
                            url=url,
                            website_name=website_name,
                            success=True,
                            extracted_data=result.data,
                            processing_time=processing_time,
                            steps_taken=total_steps
                        )
                
                # If no successful extraction yet, continue to next iteration
                if not any(r.success for r in step_results):
                    if len(failed_attempts) >= self.max_retries:
                        break
                    logger.info("Retrying with LLM guidance...")
                    continue
                
                time.sleep(1)
            
            # If we reach here, extraction wasn't successful
            processing_time = time.time() - start_time
            return WebsiteResult(
                url=url,
                website_name=website_name,
                success=False,
                error="Could not extract useful data within step limit",
                processing_time=processing_time,
                steps_taken=total_steps
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error scraping {website_name}: {str(e)}")
            return WebsiteResult(
                url=url,
                website_name=website_name,
                success=False,
                error=str(e),
                processing_time=processing_time,
                steps_taken=total_steps
            )
    
    def scrape_from_csv(self, csv_file_path: str, keywords: List[str] = None, 
                       url_column: str = "url", name_column: str = "website_name") -> Dict:
        """Scrape multiple websites from CSV file with intelligent extraction"""
        
        logger.info(f"Starting CSV-driven scraping from: {csv_file_path}")
        
        try:
            # Read CSV file
            df = pd.read_csv(csv_file_path)
            logger.info(f"Loaded {len(df)} websites from CSV")
            
            # Validate columns
            if url_column not in df.columns:
                raise ValueError(f"Column '{url_column}' not found in CSV")
            
            if name_column not in df.columns:
                logger.warning(f"Column '{name_column}' not found, using URLs as names")
                name_column = url_column
            
            results = []
            successful_extractions = 0
            
            for index, row in df.iterrows():
                url = row[url_column]
                website_name = row[name_column] if name_column in df.columns else url
                
                logger.info(f"Processing {index + 1}/{len(df)}: {website_name}")
                
                # Scrape individual website
                result = self.scrape_website_intelligently(url, website_name, keywords)
                results.append(result)
                
                if result.success:
                    successful_extractions += 1
                    logger.info(f"Successfully extracted data from {website_name}")
                else:
                    logger.warning(f"Failed to extract data from {website_name}: {result.error}")
                
                # Brief pause between websites
                time.sleep(2)
            
            # Compile final results
            final_results = {
                "summary": {
                    "total_websites": len(df),
                    "successful_extractions": successful_extractions,
                    "success_rate": f"{(successful_extractions / len(df)) * 100:.1f}%",
                    "keywords_used": keywords,
                    "processing_date": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                "individual_results": [],
                "combined_data": {}
            }
            
            # Process individual results
            for result in results:
                result_dict = {
                    "website_name": result.website_name,
                    "url": result.url,
                    "success": result.success,
                    "processing_time": result.processing_time,
                    "steps_taken": result.steps_taken
                }
                
                if result.success and result.extracted_data:
                    result_dict["extracted_data"] = result.extracted_data
                    
                    # Add to combined data
                    final_results["combined_data"][result.website_name] = result.extracted_data
                else:
                    result_dict["error"] = result.error
                
                final_results["individual_results"].append(result_dict)
            
            logger.info(f"CSV scraping completed. Success rate: {final_results['summary']['success_rate']}")
            return final_results
            
        except Exception as e:
            logger.error(f"Error in CSV scraping: {str(e)}")
            return {"error": str(e), "success": False}
    
    def save_results(self, results: Dict, output_file: str = "scraping_results.json"):
        """Save scraping results to JSON file"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving results: {str(e)}")
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

# Usage Example
def main():
    """Example usage of the enhanced CSV scraper"""
    
    # Setup AWS Bedrock client
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    # Initialize scraper
    scraper = EnhancedWebScraper(
        bedrock_client=bedrock_client,
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        headless=True  # Set to False for debugging
    )
    
    try:
        # Example: Scrape websites from CSV
        results = scraper.scrape_from_csv(
            csv_file_path="websites.csv",  # CSV with columns: url, website_name
            keywords=["python", "data science", "machine learning"],  # Keywords to search
            url_column="url",
            name_column="website_name"
        )
        
        # Save results
        scraper.save_results(results, "intelligent_scraping_results.json")
        
        # Print summary
        print("\n" + "="*60)
        print("SCRAPING SUMMARY")
        print("="*60)
        print(f"Total websites processed: {results['summary']['total_websites']}")
        print(f"Successful extractions: {results['summary']['successful_extractions']}")
        print(f"Success rate: {results['summary']['success_rate']}")
        print(f"Keywords used: {results['summary']['keywords_used']}")
        
        # Show sample extracted data
        if results['combined_data']:
            print("\nSample extracted data:")
            for website_name, data in list(results['combined_data'].items())[:2]:
                print(f"\n{website_name}:")
                print(json.dumps(data, indent=2)[:500] + "...")
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
    
    finally:
        scraper.close()

if __name__ == "__main__":
    main()