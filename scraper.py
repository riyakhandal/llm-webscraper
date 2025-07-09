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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import boto3
import json as json_module

@dataclass
class ScrapingStep:
    action: str  
    description: str
    selector: Optional[str] = None
    text_to_enter: Optional[str] = None
    expected_result: Optional[str] = None
    search_text: Optional[str] = None  # For finding elements by text content

@dataclass
class ScrapingResult:
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    next_steps: Optional[List[ScrapingStep]] = None

class WebScraper:
    def __init__(self, bedrock_client=None, model_id="anthropic.claude-3-sonnet-20240229-v1:0", 
                 aws_region="us-east-1", headless: bool = False):
        """
        Initialize scraper with AWS Bedrock
        
        Args:
            bedrock_client: Pre-configured boto3 bedrock client (optional)
            model_id: Bedrock model ID to use
            aws_region: AWS region for Bedrock
            headless: Run browser in headless mode
        """
        if bedrock_client:
            self.bedrock_client = bedrock_client
        else:
            self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        
        self.model_id = model_id
        self.driver = None
        self.max_retries = 5
        self.max_total_steps = 100
        self.search_clicked = False  # Track if search was clicked
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
        """Remove scripts, styles, and clean HTML for LLM processing"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "noscript"]):
            script.decompose()
        
        # Remove comments
        from bs4 import Comment
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        
        # Get text and preserve some structure
        cleaned_html = str(soup)
        
        # Remove excessive whitespace
        cleaned_html = re.sub(r'\s+', ' ', cleaned_html)
        cleaned_html = re.sub(r'>\s+<', '><', cleaned_html)
        print(cleaned_html.strip())
        
        return cleaned_html.strip()
    
    def find_element_by_text(self, search_text: str, timeout: int = 10):
        """Find element containing specific text"""
        try:
            # Try to find element containing the text
            xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_text.lower()}')]"
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element
        except TimeoutException:
            # Try alternative approach - find by partial text match
            try:
                elements = self.driver.find_elements(By.XPATH, "//*[text()]")
                for element in elements:
                    if search_text.lower() in element.text.lower():
                        return element
                return None
            except:
                return None
    
    def wait_for_page_load_after_search(self, timeout: int = 10):
        """Wait for page to load after search submission"""
        try:
            # Wait for URL to change or specific elements to appear
            original_url = self.driver.current_url
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                if current_url != original_url:
                    print(f"Page changed from {original_url} to {current_url}")
                    break
                time.sleep(0.5)
            
            # Additional wait for page to fully load
            time.sleep(5)
            
            # Check if page contains search results indicators
            page_source = self.driver.page_source.lower()
            result_indicators = ['results', 'search results', 'found', 'matches', 'real property']
            
            for indicator in result_indicators:
                if indicator in page_source:
                    print(f"Found result indicator: {indicator}")
                    return True
            
            return True
        except Exception as e:
            print(f"Error waiting for page load: {str(e)}")
            return False

    def get_llm_analysis(self, html_content: str, task_description: str, 
                        previous_attempts: List[str] = None) -> Dict:
        """Get LLM analysis of HTML content for scraping strategy using AWS Bedrock"""
        
        failed_attempts_context = ""
        if previous_attempts:
            failed_attempts_context = f"\n\nPrevious failed attempts:\n" + "\n".join(previous_attempts)
        
        # Enhanced prompt to handle real property search results
        prompt = f"""
        You are an expert web scraping assistant. Analyze the following HTML content and provide CSS selectors or XPath expressions to accomplish the scraping task.

        Task: {task_description}
        
        HTML Content:
        {html_content[:16000]}  
        
        {failed_attempts_context}
        
        IMPORTANT INSTRUCTIONS:
        - If this appears to be a search results page, look for elements containing "real property result search" or similar text
        - For real property searches, look for result tables, lists, or containers that hold property information
        - Common patterns for search results: tables with class containing "result", "search", "property", or divs with result data
        - After a search is submitted, the page should be allowed to load completely before extracting data
        
        Please respond with a JSON object containing:
        {{
            "steps": [
                {{
                    "action": "find_input|click|enter_text|wait|extract_data|navigate|wait_for_page_load|find_by_text",
                    "description": "Human readable description of what this step does",
                    "selector": "CSS selector or XPath (prefer CSS)",
                    "text_to_enter": "Text to enter if action is enter_text",
                    "expected_result": "What should happen after this step",
                    "search_text": "Text to search for if action is find_by_text"
                }}
            ],
            "reasoning": "Explanation of your approach",
            "confidence": "high|medium|low"
        }}
                
        Guidelines:
        - Prefer CSS selectors over XPath when possible
        - Be specific but not overly complex with selectors
        - Consider common HTML patterns (forms, buttons, inputs)
        - If you see multiple similar elements, use unique identifiers
        - For input fields, look for name, id, placeholder, or label associations
        - For buttons, look for text content, type, or class names
        - For search results, look for containers that hold multiple result items
        - Use find_by_text action when you need to locate elements by their text content
        """
        
        try:
            # Prepare the request body based on model type
            if "claude" in self.model_id.lower():
                # Claude format
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 10000,
                    "temperature": 0.5,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            elif "llama" in self.model_id.lower():
                # Llama format
                body = {
                    "prompt": prompt,
                    "max_gen_len": 1000,
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            elif "titan" in self.model_id.lower():
                # Amazon Titan format
                body = {
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": 1000,
                        "temperature": 0.1,
                        "topP": 0.9
                    }
                }
            else:
                # Generic format
                body = {
                    "prompt": prompt,
                    "max_tokens": 1000,
                    "temperature": 0.1
                }
            
            # Make the API call to Bedrock
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json_module.dumps(body),
                contentType='application/json'
            )
            
            # Parse the response based on model type
            response_body = json_module.loads(response['body'].read().decode('utf-8'))
            
            if "claude" in self.model_id.lower():
                content = response_body['content'][0]['text']
            elif "llama" in self.model_id.lower():
                content = response_body['generation']
            elif "titan" in self.model_id.lower():
                content = response_body['results'][0]['outputText']
            else:
                # Try to find text content in common response fields
                content = response_body.get('text', response_body.get('generated_text', str(response_body)))
            
            # Extract JSON from the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json_module.loads(json_match.group())
            else:
                return {"error": "Failed to parse LLM response", "raw_response": content}
                
        except Exception as e:
            return {"error": f"Bedrock API error: {str(e)}"}
    
    def execute_step(self, step: ScrapingStep) -> ScrapingResult:
        """Execute a single scraping step using Selenium"""
        try:
            print('*'*20)
            print(step)
            
            if step.action == "find_input":
                element = self.find_element(step.selector)
                if element and element.is_displayed():
                    return ScrapingResult(success=True, data={"element_found": True})
                else:
                    return ScrapingResult(success=False, error="Element not found or not visible")
            
            elif step.action == "enter_text":
                element = self.find_element(step.selector)
                if element:
                    element.clear()
                    element.send_keys(step.text_to_enter)
                    return ScrapingResult(success=True, data={"text_entered": step.text_to_enter})
                else:
                    return ScrapingResult(success=False, error="Input element not found")
            
            elif step.action == "click":
                element = self.find_element(step.selector)
                if element and element.is_enabled():
                    self.driver.execute_script("arguments[0].click();", element)
                    
                    # Check if this is a search submission
                    if "search" in step.description.lower() or "submit" in step.description.lower():
                        self.search_clicked = True
                        print("Search was clicked - will wait for page load")
                    
                    time.sleep(2)  # Wait for page response
                    return ScrapingResult(success=True, data={"clicked": True})
                else:
                    return ScrapingResult(success=False, error="Button not found or not clickable")
            
            elif step.action == "wait_for_page_load":
                success = self.wait_for_page_load_after_search()
                if success:
                    return ScrapingResult(success=True, data={"page_loaded": True})
                else:
                    return ScrapingResult(success=False, error="Page load timeout")
            
            elif step.action == "find_by_text":
                search_text = step.search_text or "real property result search"
                element = self.find_element_by_text(search_text)
                if element:
                    return ScrapingResult(success=True, data={
                        "element_found": True, 
                        "element_text": element.text,
                        "element_tag": element.tag_name
                    })
                else:
                    return ScrapingResult(success=False, error=f"Element with text '{search_text}' not found")
            
            elif step.action == "extract_data":
                
                if not step.selector or step.selector == "":
                    possible_selectors = [
                        "[class*='result']",
                        "[class*='search']",
                        "[class*='property']",
                        "table tr",
                        ".result-item",
                        ".search-result",
                        ".property-result"
                    ]
                    
                    elements = []
                    for selector in possible_selectors:
                        try:
                            found_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            if found_elements:
                                elements = found_elements
                                print(f"Found elements with selector: {selector}")
                                break
                        except:
                            continue
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, step.selector)
                
                if elements:
                    data = []
                    for elem in elements:
                        element_data = {
                            "text": elem.text.strip(),
                            "html": elem.get_attribute("outerHTML")
                        }
                        # Only include elements that have meaningful content
                        if element_data["text"] and len(element_data["text"]) > 10:
                            data.append(element_data)
                    
                    print(f"Extracted {len(data)} data items")
                    return ScrapingResult(success=True, data={"extracted_data": data})
                else:
                    return ScrapingResult(success=False, error="No data elements found")
            
            elif step.action == "navigate":
                if step.selector.startswith("http"):
                    self.driver.get(step.selector)
                    time.sleep(3)
                    return ScrapingResult(success=True, data={"navigated": True})
                else:
                    return ScrapingResult(success=False, error="Invalid URL")
                
            elif step.action == "wait":
                wait_time = 5  # Default wait time
                if step.text_to_enter:
                    try:
                        wait_time = int(step.text_to_enter)
                    except:
                        wait_time = 5
                time.sleep(wait_time)
                return ScrapingResult(success=True, data={"waited": wait_time})
                    
        except Exception as e:
            return ScrapingResult(success=False, error=f"Selenium error: {str(e)}")
    
    def find_element(self, selector: str, timeout: int = 10):
        """Find element with improved error handling"""
        try:
            # Try CSS selector first
            if selector.startswith("//"):
                # XPath
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
            else:
                # CSS Selector
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            return element
        except TimeoutException:
            return None
    
    def scrape_with_intelligence(self, url: str, task_description: str, 
                               keywords: List[str] = None) -> Dict:
        """Main scraping function with LLM guidance"""
        
        total_steps = 0
        failed_attempts = []
        current_url = url
        
        self.driver.get(current_url)
        time.sleep(3)
        
        # Enhanced task description with keywords and real property search context
        if keywords:
            enhanced_task = f"{task_description}. Keywords to search: {', '.join(keywords)}. After clicking search, wait 5 seconds and look for elements containing 'real property result search'."
       
        while total_steps < self.max_total_steps:

            html_content = self.driver.page_source
            cleaned_html = self.clean_html(html_content)
            
            # Step 3: Get LLM analysis
            llm_response = self.get_llm_analysis(
                cleaned_html, 
                enhanced_task, 
                failed_attempts[-3:]  # Include last 3 failures for context
            )

            print(llm_response)
            
            if "error" in llm_response:
                return {"success": False, "error": llm_response["error"]}
            
            # Step 4: Execute LLM-suggested steps
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
                
                # Add keywords to text entry if it's an input field
                if step.action == "enter_text" and keywords and not step.text_to_enter:
                    step.text_to_enter = keywords[0]  # Use first keyword
                elif step.action == "enter_text" and keywords and step.text_to_enter:
                    # Replace placeholder with actual keyword
                    if "[KEYWORD]" in step.text_to_enter:
                        step.text_to_enter = step.text_to_enter.replace("[KEYWORD]", keywords[0])
                
                print(f"Step {total_steps + 1}: {step.description}")
                result = self.execute_step(step)
                step_results.append(result)
                total_steps += 1
                
                # Special handling after search is clicked
                if self.search_clicked and step.action == "click":
                    print("Search was clicked, waiting for page load...")
                    self.wait_for_page_load_after_search()
                    self.search_clicked = False
                    
                    # Try to find real property search results
                    real_property_element = self.find_element_by_text("real property result search")
                    if real_property_element:
                        print("Found real property search results element!")
                        # Extract data from this context
                        parent_element = real_property_element.find_element(By.XPATH, "..")
                        result.data = {
                            "real_property_found": True,
                            "element_text": real_property_element.text,
                            "parent_html": parent_element.get_attribute("outerHTML")
                        }
                
                if not result.success:
                    failed_attempts.append(f"Step: {step.description}, Selector: {step.selector}, Error: {result.error}")
                    print(f"Step failed: {result.error}")
                    break
                else:
                    print(f"Step succeeded: {step.description}")
                
                # Check if we've reached a results page
                if "extract_data" in step.action and result.success:
                    return {
                        "success": True,
                        "data": result.data,
                        "total_steps": total_steps,
                        "final_url": self.driver.current_url
                    }
            
            # If all steps in this iteration failed, try again with LLM correction
            if not any(r.success for r in step_results):
                if len(failed_attempts) >= self.max_retries:
                    break
                print("All steps failed, requesting LLM correction...")
                continue
            
            # Wait a bit before next iteration
            time.sleep(2)
        
        # If we've exhausted all attempts
        return {
            "success": False,
            "error": "Maximum attempts reached without successful completion",
            "failed_attempts": failed_attempts,
            "total_steps": total_steps
        }
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

# Usage Example
def main():
    # Initialize AWS Bedrock client
    # Make sure you have AWS credentials configured (AWS CLI, environment variables, or IAM role)
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    
    # Initialize scraper with Bedrock
    scraper = IntelligentWebScraper(
        bedrock_client=bedrock_client,
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",  # or other available models
        headless=False
    )
    
    try:
        # Example usage
        result = scraper.scrape_with_intelligence(
            url="https://example-search-site.com",
            task_description="Find the search input field, enter a keyword, submit the search, and extract the results from the results page",
            keywords=["python programming", "data science"]
        )
        
        print("Scraping Result:")
        print(json.dumps(result, indent=2))
        
    finally:
        scraper.close()

if __name__ == "__main__":
    main()