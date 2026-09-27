import json
import logging
from typing import Dict, Any, Generator, List

from src.tools.aws_clients import BedrockClient
from src.tools.qdrant_search import QdrantDiagnosticSearch
from src.tools.sqlite_history import get_service_history

logger = logging.getLogger(__name__)

# Define the tools available to Bedrock
TOOL_DEFINITIONS = [
    {
        "toolSpec": {
            "name": "qdrant_search",
            "description": "Search the diagnostic knowledge base for repair manuals and decision trees.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "symptom_text": {"type": "string"},
                        "dtc_codes": {"type": "array", "items": {"type": "string"}},
                        "make": {"type": "string"}
                    },
                    "required": ["symptom_text"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "sqlite_history",
            "description": "Look up past service history and confirmed fixes for a specific VIN.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "vin": {"type": "string"}
                    },
                    "required": ["vin"]
                }
            }
        }
    }
]

SYSTEM_PROMPT = """You are a Vehicle Fault Diagnosis Agent. 
You must analyze the vehicle's symptoms, DTC codes, and inspection photos.
You have a maximum of 3 turns to reach a conclusion. Use the provided tools to lookup manuals and history.
If the issue involves brakes, steering, airbags, or EV high-voltage, you MUST set escalation_required to true.
If confidence is < 0.5, set escalation_required to true and recommend tests instead of guessing."""

class ReActOrchestrator:
    def __init__(self):
        self.bedrock = BedrockClient()
        self.qdrant = QdrantDiagnosticSearch()
        
    def run_diagnosis(self, request_data: Dict[str, Any]) -> Generator[str, None, None]:
        """
        Executes a strict 3-turn ReAct loop and yields SSE-compatible JSON strings.
        """
        turn_budget = 3
        
        # Build initial message
        content_blocks = []
        content_blocks.append({"text": f"Symptom: {request_data.get('symptom_text')}\nVIN: {request_data.get('vin')}\nDTCs: {request_data.get('dtc_codes')}"})
        
        messages = [{"role": "user", "content": content_blocks}]
        
        for turn in range(turn_budget):
            try:
                response = self.bedrock.converse(
                    messages=messages,
                    system_prompts=[{"text": SYSTEM_PROMPT}],
                    tools=TOOL_DEFINITIONS
                )
            except Exception as e:
                yield json.dumps({"event": "error", "data": "Cloud Unreachable or API Error"})
                return
                
            output_msg = response.get('output', {}).get('message', {})
            messages.append(output_msg)
            
            # Check for tool requests
            tool_calls = [block.get('toolUse') for block in output_msg.get('content', []) if 'toolUse' in block]
            
            if not tool_calls:
                # No tools called, the agent has provided a final answer (hopefully JSON)
                final_text = next((block['text'] for block in output_msg.get('content', []) if 'text' in block), "")
                
                # Check for safety escalation keywords in the final output
                safety_categories = ["brake", "steering", "airbag", "ev high-voltage"]
                escalation = False
                for cat in safety_categories:
                    if cat in final_text.lower():
                        escalation = True
                        yield json.dumps({"event": "escalation", "data": {"reason": f"Detected safety critical system: {cat}", "category": cat}})
                
                # Yield final done event (M11 format)
                yield json.dumps({
                    "event": "done",
                    "data": {
                        "job_id": "dummy_job_id",
                        "ranked_causes": [{"cause": final_text, "confidence": 0.9, "evidence": []}],
                        "confirmation_tests": [],
                        "parts_estimate": [],
                        "labour_estimate_hours": 2,
                        "safety_flags": [],
                        "escalation_required": escalation
                    }
                })
                return
                
            # Execute Tools
            tool_results = []
            for tool in tool_calls:
                tool_name = tool['name']
                tool_inputs = tool['input']
                
                # Yield SSE Step event
                yield json.dumps({"event": "step", "data": {"step_no": turn + 1, "tool_used": tool_name, "key_inputs": tool_inputs}})
                
                result_data = {}
                if tool_name == "qdrant_search":
                    result_data = self.qdrant.search(**tool_inputs)
                    if result_data:
                        yield json.dumps({"event": "evidence", "data": {"source": result_data[0]['source'], "chunk_id": result_data[0]['chunk_id'], "snippet_ref": result_data[0]['payload']['text']}})
                elif tool_name == "sqlite_history":
                    # Calling the function from DB module created by subagent
                    # Need a db connection here, but we will mock it for the orchestrator test
                    result_data = {"history": "No major past repairs found."}
                
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool['toolUseId'],
                        "content": [{"json": result_data}]
                    }
                })
                
            # Append tool results to messages for the next turn
            messages.append({"role": "user", "content": tool_results})
            yield json.dumps({"event": "confidence", "data": {"value": 0.8}}) # Mock confidence update
            
        # If loop finishes without returning, budget exhausted
        yield json.dumps({"event": "done", "data": {"escalation_required": True, "ranked_causes": [{"cause": "Insufficient evidence, run these tests first", "confidence": 0.1, "evidence": []}]}})
