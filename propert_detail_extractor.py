import time
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from openai import OpenAI
from test import *
from constants import OPENAI_API

class LLMPropertyExtractor:
    """Handles property details extraction using LLM"""
    
    def __init__(self, openai_client: OpenAI, model_name: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model_name = model_name
    
    def extract_property_details(self, raw_data: List[Dict], site_purpose: str) -> Dict[str, Any]:
        """Extract structured property details from raw scraped data"""
        
        # Combine all text data
        all_text = []
        for item in raw_data:
            if item.get("text"):
                all_text.append(item["text"])
        
        combined_text = "\n".join(all_text)
        
        prompt = f"""
        Analyze the following scraped data from a {site_purpose} website and extract structured property information.

        Raw Data:
        {combined_text[:8000]}

        Extract the following information if available (return null if not found):
        - Property address
        - Owner name(s)
        - Property value/assessment value
        - Tax amount
        - Property type/description
        - Lot/parcel information
        - Square footage/acreage
        - Year built
        - Any fees or charges
        - Any dates (tax due dates, assessment dates, etc.)
        - Any other relevant property details

        Respond with a JSON object containing the extracted information:
        {{
            "address": "property address or null",
            "owner_name": "owner name or null",
            "property_value": "assessment/market value or null",
            "tax_amount": "tax amount or null",
            "property_type": "property description/type or null",
            "lot_info": "lot/parcel details or null",
            "square_footage": "size information or null",
            "year_built": "construction year or null",
            "fees_charges": "additional fees or null",
            "important_dates": "relevant dates or null",
            "additional_details": "any other relevant information or null"
        }}

        NOTE: Return valid JSON only. If a field is not found, use null.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured property information from web data. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            content = re.sub(r'^```json\n|\n```$', '', content, flags=re.MULTILINE)
            print('*'*10 , 'PROPERT DETAIL Extractor')
            print(json.loads(content))
            
            return json.loads(content)
        except Exception as e:
            return {"error": f"Failed to extract property details: {str(e)}"}