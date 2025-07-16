# CSV Scraper Usage Examples and Setup

import boto3
import pandas as pd
import json
from pathlib import Path
from enhanced_scraper import EnhancedWebScraper

# Example 1: Basic CSV Setup
def create_sample_csv():
    """Create a sample CSV file with websites to scrape"""
    
    sample_websites = [
    ]
    
    df = pd.DataFrame(sample_websites)
    df.to_csv("websites.csv", index=False)
    print("Sample CSV created: websites.csv")
    return df

# Example 2: Simple CSV Scraping
def simple_csv_scraping():
    """Basic example of CSV scraping with keywords"""
    
    # Create sample CSV if it doesn't exist
    if not Path("websites.csv").exists():
        create_sample_csv()
    
    # Setup AWS Bedrock client
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    # Initialize scraper
    scraper = EnhancedWebScraper(
        bedrock_client=bedrock_client,
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        headless=True
    )
    
    try:
        # Scrape with keywords
        results = scraper.scrape_from_csv(
            csv_file_path="websites.csv",
            keywords=["John Smith", "contact information", "services"],
            url_column="url",
            name_column="website_name"
        )
        
        # Save and display results
        scraper.save_results(results, "simple_scraping_results.json")
        
        print("Simple scraping completed!")
        print(f"Success rate: {results['summary']['success_rate']}")
        
        return results
        
    finally:
        scraper.close()

# Example 3: Advanced CSV Scraping with Custom Configuration
def advanced_csv_scraping():
    """Advanced example with custom configuration"""
    
    # Custom scraper configuration
    class CustomScraper(EnhancedWebScraper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.max_total_steps = 10  # Allow more steps for complex sites
            self.max_retries = 5       # More retries for difficult sites
        
        def scrape_website_intelligently(self, url, website_name="", keywords=None):
            """Override with custom logic if needed"""
            print(f"\n🔍 Starting advanced scraping of: {website_name}")
            print(f"🎯 Keywords: {keywords}")
            
            # Call parent method with enhanced logging
            result = super().scrape_website_intelligently(url, website_name, keywords)
            
            if result.success:
                print(f"✅ Successfully extracted from {website_name}")
                print(f"⏱️ Processing time: {result.processing_time:.2f} seconds")
                print(f"🔧 Steps taken: {result.steps_taken}")
            else:
                print(f"❌ Failed to extract from {website_name}: {result.error}")
            
            return result
    
    # Setup with custom configuration
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    
    scraper = CustomScraper(
        bedrock_client=bedrock_client,
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        headless=True
    )
    
    try:
        # Advanced scraping with multiple keyword sets
        results = scraper.scrape_from_csv(
            csv_file_path="websites.csv",
            keywords=["CREST, CAMERON", "real property", "search results"],
            url_column="url",
            name_column="website_name"
        )
        
        # Enhanced results processing
        scraper.save_results(results, "advanced_scraping_results.json")
        
        # Generate detailed report
        generate_detailed_report(results)
        
        return results
        
    finally:
        scraper.close()

# Example 4: Real Estate Specific Scraping
def real_estate_csv_scraping():
    """Specialized example for real estate websites"""
    
    # Real estate specific CSV
    real_estate_sites = [
    ]
    
    df = pd.DataFrame(real_estate_sites)
    df.to_csv("real_estate_websites.csv", index=False)
    
    # Setup scraper
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    scraper = EnhancedWebScraper(bedrock_client=bedrock_client, headless=True)
    
    try:
        # Real estate specific keywords
        real_estate_keywords = [
            "CREST, CAMERON",
            "CRAWFORD, AUTUMN",
        ]
        
        results = scraper.scrape_from_csv(
            csv_file_path="real_estate_websites.csv",
            keywords=real_estate_keywords,
            url_column="url",
            name_column="website_name"
        )
        
        # Process real estate specific data
        real_estate_data = process_real_estate_data(results)
        
        # Save specialized results
        with open("real_estate_results.json", "w") as f:
            json.dump(real_estate_data, f, indent=2)
        
        print("Real estate scraping completed!")
        return real_estate_data
        
    finally:
        scraper.close()

# Example 5: Batch Processing with Error Recovery
def batch_scraping_with_recovery():
    """Example with error recovery and batch processing"""
    
    # Setup
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
    scraper = EnhancedWebScraper(bedrock_client=bedrock_client, headless=True)
    
    try:
        # Read CSV
        df = pd.read_csv("websites.csv")
        
        # Process in batches
        batch_size = 5
        all_results = []
        
        for i in range(0, len(df), batch_size):
            batch_df = df.iloc[i:i+batch_size]
            print(f"\n🔄 Processing batch {i//batch_size + 1}")
            
            # Create temporary CSV for batch
            batch_csv = f"batch_{i//batch_size + 1}.csv"
            batch_df.to_csv(batch_csv, index=False)
            
            try:
                # Process batch
                batch_results = scraper.scrape_from_csv(
                    csv_file_path=batch_csv,
                    keywords=["search term", "information", "data"],
                    url_column="url",
                    name_column="website_name"
                )
                
                all_results.append(batch_results)
                
                # Save batch results
                scraper.save_results(batch_results, f"batch_{i//batch_size + 1}_results.json")
                
            except Exception as e:
                print(f"❌ Error in batch {i//batch_size + 1}: {str(e)}")
                continue
            
            # Clean up temporary file
            Path(batch_csv).unlink(missing_ok=True)
            
            # Brief pause between batches
            import time
            time.sleep(5)
        
        # Combine all results
        combined_results = combine_batch_results(all_results)
        scraper.save_results(combined_results, "final_combined_results.json")
        
        return combined_results
        
    finally:
        scraper.close()

# Helper Functions
def generate_detailed_report(results):
    """Generate a detailed HTML report of scraping results"""
    
    html_report = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Web Scraping Results Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .summary {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            .website {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
            .data {{ background-color: #f9f9f9; padding: 10px; font-family: monospace; }}
        </style>
    </head>
    <body>
        <h1>Web Scraping Results Report</h1>
        
        <div class="summary">
            <h2>Summary</h2>
            <p><strong>Total Websites:</strong> {results['summary']['total_websites']}</p>
            <p><strong>Successful Extractions:</strong> {results['summary']['successful_extractions']}</p>
            <p><strong>Success Rate:</strong> {results['summary']['success_rate']}</p>
            <p><strong>Keywords Used:</strong> {', '.join(results['summary']['keywords_used']) if results['summary']['keywords_used'] else 'None'}</p>
            <p><strong>Processing Date:</strong> {results['summary']['processing_date']}</p>
        </div>
        
        <h2>Individual Results</h2>
    """
    
    for result in results['individual_results']:
        status_class = "success" if result['success'] else "error"
        html_report += f"""
        <div class="website">
            <h3 class="{status_class}">{result['website_name']}</h3>
            <p><strong>URL:</strong> {result['url']}</p>
            <p><strong>Status:</strong> <span class="{status_class}">{'Success' if result['success'] else 'Failed'}</span></p>
            <p><strong>Processing Time:</strong> {result.get('processing_time', 'N/A')} seconds</p>
            <p><strong>Steps Taken:</strong> {result.get('steps_taken', 'N/A')}</p>
        """
        
        if result['success'] and 'extracted_data' in result:
            html_report += f"""
            <div class="data">
                <strong>Extracted Data:</strong><br>
                <pre>{json.dumps(result['extracted_data'], indent=2)[:1000]}...</pre>
            </div>
            """
        elif not result['success']:
            html_report += f"""
            <p class="error"><strong>Error:</strong> {result.get('error', 'Unknown error')}</p>
            """
        
        html_report += "</div>"
    
    html_report += """
    </body>
    </html>
    """
    
    with open("scraping_report.html", "w") as f:
        f.write(html_report)
    
    print("📄 Detailed report generated: scraping_report.html")

def process_real_estate_data(results):
    """Process and structure real estate specific data"""
    
    processed_data = {
        "real_estate_summary": {
            "total_properties_found": 0,
            "successful_searches": 0,
            "property_details": []
        },
        "by_website": {}
    }
    
    for result in results['individual_results']:
        if result['success'] and 'extracted_data' in result:
            website_data = result['extracted_data']
            
            # Extract property-specific information
            if 'extracted_data' in website_data:
                structured_data = website_data['extracted_data'].get('structured_data', [])
                
                property_info = {
                    "website": result['website_name'],
                    "url": result['url'],
                    "properties": []
                }
                
                for item in structured_data:
                    if any(keyword in item.get('content', '').lower() for keyword in ['property', 'real estate', 'land', 'address']):
                        property_info['properties'].append(item)
                        processed_data['real_estate_summary']['total_properties_found'] += 1
                
                if property_info['properties']:
                    processed_data['real_estate_summary']['successful_searches'] += 1
                    processed_data['by_website'][result['website_name']] = property_info
    
    return processed_data

def combine_batch_results(batch_results_list):
    """Combine multiple batch results into a single result set"""
    
    combined = {
        "summary": {
            "total_websites": 0,
            "successful_extractions": 0,
            "success_rate": "0%",
            "keywords_used": [],
            "processing_date": batch_results_list[0]['summary']['processing_date'] if batch_results_list else ""
        },
        "individual_results": [],
        "combined_data": {}
    }
    
    for batch_result in batch_results_list:
        combined['summary']['total_websites'] += batch_result['summary']['total_websites']
        combined['summary']['successful_extractions'] += batch_result['summary']['successful_extractions']
        combined['individual_results'].extend(batch_result['individual_results'])
        combined['combined_data'].update(batch_result['combined_data'])
        
        # Combine keywords
        if batch_result['summary']['keywords_used']:
            combined['summary']['keywords_used'].extend(batch_result['summary']['keywords_used'])
    
    # Remove duplicate keywords
    combined['summary']['keywords_used'] = list(set(combined['summary']['keywords_used']))
    
    # Calculate overall success rate
    if combined['summary']['total_websites'] > 0:
        success_rate = (combined['summary']['successful_extractions'] / combined['summary']['total_websites']) * 100
        combined['summary']['success_rate'] = f"{success_rate:.1f}%"
    
    return combined

# Example usage functions
def quick_start():
    """Quick start example for immediate use"""
    
    print("🚀 Quick Start CSV Scraping")
    print("=" * 50)
    
    # Create sample CSV if needed
    if not Path("websites.csv").exists():
        create_sample_csv()
    
    # Run simple scraping
    results = simple_csv_scraping()
    
    print(f"\n✅ Scraping completed!")
    print(f"📊 Check 'simple_scraping_results.json' for detailed results")
    print(f"🎯 Success rate: {results['summary']['success_rate']}")
    
    return results

def main():
    """Main function demonstrating different usage patterns"""
    
    print("🤖 Enhanced Web Scraper with LLM Intelligence")
    print("=" * 60)
    
    # Example options
    examples = {
        "1": ("Quick Start", quick_start),
        "2": ("Simple CSV Scraping", simple_csv_scraping),
        "3": ("Advanced CSV Scraping", advanced_csv_scraping),
        "4": ("Real Estate Scraping", real_estate_csv_scraping),
        "5": ("Batch Processing", batch_scraping_with_recovery)
    }
    
    print("\nAvailable Examples:")
    for key, (name, _) in examples.items():
        print(f"{key}. {name}")
    
    choice = input("\nSelect an example (1-5) or press Enter for Quick Start: ").strip()
    
    if not choice:
        choice = "1"
    
    if choice in examples:
        name, func = examples[choice]
        print(f"\n🏃 Running: {name}")
        try:
            result = func()
            print(f"\n✅ {name} completed successfully!")
            return result
        except Exception as e:
            print(f"\n❌ Error in {name}: {str(e)}")
    else:
        print("❌ Invalid choice. Running Quick Start...")
        return quick_start()

if __name__ == "__main__":
    main()