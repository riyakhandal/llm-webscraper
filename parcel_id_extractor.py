
import time
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from openai import OpenAI
from test import *
from constants import OPENAI_API


class LLMParcelExtractor:
    """Handles parcel ID extraction using LLM"""
    
    def __init__(self, openai_client: OpenAI, model_name: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model_name = model_name
    
    def extract_parcel_ids(self, raw_data: List[Dict]) -> List[str]:
        """Extract parcel IDs, APN numbers, or similar identifiers using LLM"""
        
        # Combine all text data
        all_text = []
        for item in raw_data:
            if item.get("text"):
                all_text.append(item["text"])
        
        combined_text = "\n".join(all_text)
        
        prompt = f"""
        Analyze the following text data and extract all parcel IDs, APN numbers, property identification numbers, or similar unique property identifiers.

        Text Data:
        {combined_text[:8000]}

        Look for patterns that could be property identifiers such as:
        - Parcel numbers (various formats)
        - APN (Assessor's Parcel Number)
        - Property ID numbers
        - Tax parcel numbers
        - Any alphanumeric codes that appear to identify properties

        Extract ALL possible identifiers and return them as a JSON array of strings:
        {{
            "parcel_ids": ["id1", "id2", "id3", ...]
        }}

        If no identifiers are found, return:
        {{
            "parcel_ids": []
        }}

        NOTE: Return valid JSON only.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying property parcel IDs and similar identifiers from text data. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            content = re.sub(r'^```json\n|\n```$', '', content, flags=re.MULTILINE)
            print('*'*10 , 'PARCEL EXTRACTOR')
            print(json.loads(content))
            
            result = json.loads(content)
            return result.get("parcel_ids", [])
        except Exception as e:
            print(f"Failed to extract parcel IDs: {str(e)}")
            return []
