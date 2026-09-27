import pytest
import json
from unittest.mock import MagicMock, patch
from src.agents.orchestrator import ReActOrchestrator

@patch('src.agents.orchestrator.BedrockClient')
@patch('src.agents.orchestrator.QdrantDiagnosticSearch')
def test_orchestrator_yields_done_event(MockQdrant, MockBedrock):
    # Setup mocks
    mock_bedrock_instance = MockBedrock.return_value
    
    # Simulate a Bedrock response with a final answer (no tool calls)
    mock_bedrock_instance.converse.return_value = {
        'output': {
            'message': {
                'content': [{'text': 'Check the brake pads for wear.'}]
            }
        }
    }
    
    orchestrator = ReActOrchestrator()
    request_data = {"symptom_text": "Squeaking noise when stopping", "vin": "12345", "dtc_codes": []}
    
    events = list(orchestrator.run_diagnosis(request_data))
    
    # Should yield a single escalation event (because "brake" is in the text) and a done event
    assert len(events) == 2
    
    escalation_event = json.loads(events[0])
    assert escalation_event['event'] == 'escalation'
    assert 'brake' in escalation_event['data']['category']
    
    done_event = json.loads(events[1])
    assert done_event['event'] == 'done'
    assert done_event['data']['escalation_required'] == True
    assert 'Check the brake pads' in done_event['data']['ranked_causes'][0]['cause']

@patch('src.agents.orchestrator.BedrockClient')
def test_orchestrator_budget_exhaustion(MockBedrock):
    # Setup mocks
    mock_bedrock_instance = MockBedrock.return_value
    
    # Simulate an infinite loop of tool calls
    mock_bedrock_instance.converse.return_value = {
        'output': {
            'message': {
                'content': [
                    {
                        'toolUse': {
                            'toolUseId': 'tool_1',
                            'name': 'qdrant_search',
                            'input': {'symptom_text': 'engine noise'}
                        }
                    }
                ]
            }
        }
    }
    
    orchestrator = ReActOrchestrator()
    events = list(orchestrator.run_diagnosis({"symptom_text": "noise"}))
    
    # We should have 3 turns. Each turn yields 'step', 'evidence', 'confidence'.
    # Finally, the loop ends and yields 'done' indicating exhaustion.
    done_event = json.loads(events[-1])
    assert done_event['event'] == 'done'
    assert done_event['data']['escalation_required'] == True
    assert 'Insufficient evidence' in done_event['data']['ranked_causes'][0]['cause']
