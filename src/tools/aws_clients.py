import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional
import json
import logging
from src.core.config import settings

logger = logging.getLogger(__name__)

class BedrockClient:
    def __init__(self):
        # Fallback to local region if not specified
        self.client = boto3.client('bedrock-runtime', region_name=settings.AWS_REGION)
        self.model_id = settings.BEDROCK_MODEL_ID
    
    def converse(
        self, 
        messages: List[Dict[str, Any]], 
        system_prompts: Optional[List[Dict[str, str]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Calls the Bedrock Converse API with strict cost controls.
        """
        kwargs = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": 2048, # Strict limit to prevent budget blowout
                "temperature": 0.2,
            }
        }
        
        if system_prompts:
            kwargs["system"] = system_prompts
            
        if tools:
            kwargs["toolConfig"] = {
                "tools": tools,
                "toolChoice": {"auto": {}}
            }
            
        try:
            response = self.client.converse(**kwargs)
            
            # Token logging for W9 cost control requirements
            usage = response.get('usage', {})
            logger.info(f"Bedrock Token Usage: Input={usage.get('inputTokens', 0)}, Output={usage.get('outputTokens', 0)}, Total={usage.get('totalTokens', 0)}")
            
            return response
            
        except ClientError as e:
            logger.error(f"Bedrock API Error: {e}")
            raise e
