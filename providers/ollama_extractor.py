import json
import ollama
from typing import Dict, Any
from core.interfaces import IExtractor

class OllamaExtractor(IExtractor):
    def __init__(self, model_name: str):
        self.model_name = model_name

    def extract(self, schema: Dict[str, Any], text: str) -> Dict[str, Any]:
        prompt = f"""
        Extract the following fields from the provided text according to this JSON schema.
        Respond ONLY with valid JSON matching exactly the keys in the schema. Do not include markdown formatting, code blocks, or extra commentary.
        If a field is not found in the text, set its value to null.
        
        Schema:
        {json.dumps(schema, indent=2)}
        
        Text:
        {text[:8000]} # Truncated for context limits
        """
        
        try:
            response = ollama.chat(model=self.model_name, messages=[
                {'role': 'system', 'content': 'You are a precise data extraction system. You only output valid JSON without any markdown formatting like ```json.'},
                {'role': 'user', 'content': prompt}
            ])
            
            content = response['message']['content'].strip()
            # Clean up potential markdown formatting just in case
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
                
            return json.loads(content.strip())
        except Exception as e:
            raise Exception(f"Extraction failed with Ollama: {str(e)}")
