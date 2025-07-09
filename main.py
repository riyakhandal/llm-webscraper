from scraper import WebScraper
from test import TEST_URL
import boto3
import json

BEDROCK_MODELS = {
    "claude_3_sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
   }

def setup_aws_credentials():
    """
    Setup AWS credentials for Bedrock access
    you can use any of these methods:
    
    1. AWS CLI: aws configure
    2. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    3. IAM roles (for EC2 instances)
    4. AWS credentials file (~/.aws/credentials)
    """
    pass

def create_bedrock_scraper(model_choice="claude_3_sonnet", aws_region="us-west-2"):
    """Create a Bedrock-powered web scraper"""
    
    bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
    
    model_id = BEDROCK_MODELS.get(model_choice, BEDROCK_MODELS["claude_3_sonnet"])
    
    scraper = WebScraper(
        bedrock_client=bedrock_client,
        model_id=model_id,
        aws_region=aws_region,
        headless=False
    )
    
    return scraper


def scrape_with_claude_sonnet():    
    scraper = create_bedrock_scraper("claude_3_sonnet")
    
    try:
        result = scraper.scrape_with_intelligence(
            url=TEST_URL,
            task_description="""
            1. Find the input field on the homepage
            2. Enter the provided keyword
            3. Click the search button or submit the form
            4. Wait for the results page to load
            5. Extract the results and return a json like this:
            { 
                '<table header1'>: <'table data1'>,
                '<table header2'>: <'table data2'>,
                '<table header3'>: <'table data3'>,
                ...
            }
            """,
            keywords=["CRAWFORD, AUTUMN"]
        )
        
        if result["success"]:
            print("Scraping completed successfully!")
            print(f"Extracted data: {json.dumps(result['data'], indent=2)}")
            print(f"Final URL: {result['final_url']}")
            print(f"Total steps taken: {result['total_steps']}")
        else:
            print("Scraping failed:")
            print(f"Error: {result['error']}")
            if 'failed_attempts' in result:
                print("Failed attempts:", result['failed_attempts'])
        
        return result
        
    finally:
        scraper.close()


def scrape_with_retry_logic():
    """Example with enhanced retry logic for difficult websites"""
    
    class EnhancedBedrockScraper(WebScraper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.max_retries = 8  # Increase retries for complex sites
            self.max_total_steps = 150  # Allow more steps
        
        def scrape_with_intelligence(self, url, task_description, keywords=None):
            """Enhanced scraping with better error handling"""
            
            print(f"Starting intelligent scraping of: {url}")
            print(f"Task: {task_description}")
            print(f"Keywords: {keywords}")
            print(f"Using model: {self.model_id}")
            
            result = super().scrape_with_intelligence(url, task_description, keywords)
            
            # Enhanced logging
            if result["success"]:
                print(f"Success after {result['total_steps']} steps")
            else:
                print(f"Failed after {result.get('total_steps', 0)} steps")
                print(f"Consider trying a different model or approach")
            
            return result
    
    # Use enhanced scraper
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    scraper = EnhancedBedrockScraper(
        bedrock_client=bedrock_client,
        model_id=BEDROCK_MODELS["claude_3_opus"],  # Use most capable model
        headless=False
    )
    
    try:
        result = scraper.scrape_with_intelligence(
            url="https://complex-spa-website.com",
            task_description="Navigate complex single-page application and extract data",
            keywords=["specific search term"]
        )
        return result
    finally:
        scraper.close()

if __name__ == "__main__":
    print("\n" + "="*50)
    print("Let's Start")
        
    print("\nUsing Claude 3 Sonnet...")
    scrape_with_claude_sonnet()
        