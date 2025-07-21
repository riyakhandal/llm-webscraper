import time
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from openai import OpenAI
from test import *
from constants import OPENAI_API


class LLMScrapingStrategy:
    """Handles scraping strategy generation using LLM"""
    
    def __init__(self, openai_client: OpenAI, model_name: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model_name = model_name
    
    def get_scraping_strategy(self, html_content: str, task_description: str, 
                            keywords: List[str] = None, previous_attempts: List[str] = None,
                            search_completed: bool = False) -> Dict:
        """Generate scraping strategy using LLM analysis"""
        
        failed_attempts_context = ""
        if previous_attempts:
            failed_attempts_context = f"\n\nPrevious failed attempts:\n" + "\n".join(previous_attempts)
        
        keywords_context = f"\nKeywords to use: {', '.join(keywords)}" if keywords else ""
        
        search_status_context = ""
        if search_completed:
            search_status_context = """
            
            IMPORTANT: A search has already been completed successfully. DO NOT perform another search.
            The current page should contain search results. Focus ONLY on extracting data from the current page.
            Look for tables, divs, or other elements that contain the information we need.
            Do not interact with input fields or search buttons again.
            """
        
        prompt = f"""
        You are an expert web scraping assistant. Analyze the provided HTML content and generate a strategy to accomplish the scraping task.

        Task: {task_description}
        HTML Content: {html_content[:16000]}
        {keywords_context}
        {search_status_context}
        {failed_attempts_context}

        IMPORTANT INSTRUCTIONS:
        - Generate a sequence of actionable steps to complete the task
        - Focus on identifying the correct elements to interact with
        - If search has been completed, ONLY extract data - do not search again
        - Generate steps to:
          1. If no search completed: Find input fields, enter keywords, submit form
          2. If search completed: Extract data from results (any visible content)
          3. Wait for results to load if needed
          4. Extract ALL visible and relevant content from the page
        - While searching for input fields, If there are multiple input fields on the same page:
          1. Search input fields which are related to property search. They should have input fields for name or address or parcel id.
          2. Enter the name or id whatever is provided to you in the corresponding field.
        - Look for any elements that might contain the data we need
        - You will be provided one of these:
          1. parcel_id
          2. borrower name
          3. address
          You have to figure out which thing is provided and should enter that in the input field accordingly.

        Respond with a JSON object:
        {{
            "steps": [
                {{
                    "action": "navigate|find_input|enter_text|click|wait|wait_for_page_load|find_by_text|extract_data",
                    "description": "Human-readable description of the step",
                    "selector": "CSS selector or XPath (if CSS is not feasible)",
                    "text_to_enter": "Text to enter for enter_text action",
                    "expected_result": "Expected outcome of the step",
                    "search_text": "Text to search for find_by_text action"
                }}
            ],
            "reasoning": "Explanation of the approach",
            "confidence": "high|medium|low"
        }}

        NOTE: The response should be valid JSON. No comments or special characters.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert web scraping assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.3
            )
            content = response.choices[0].message.content
            content = re.sub(r'^```json\n|\n```$', '', content, flags=re.MULTILINE).strip()
            print('*'*10 , 'SCRAPING')
            
            if content:
                print(json.loads(content))
                return json.loads(content)
            return {"error": "Failed to parse LLM response", "raw_response": content}
        except Exception as e:
            return {"error": f"OpenAI API error: {str(e)}"}