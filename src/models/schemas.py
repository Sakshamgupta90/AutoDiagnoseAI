from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from enum import Enum

class DiagnosisRequest(BaseModel):
    vin: Optional[str] = Field(None, description="Vehicle Identification Number")
    make: str = Field(..., description="Vehicle Make")
    model: str = Field(..., description="Vehicle Model")
    year: Optional[int] = Field(None, description="Vehicle Year")
    dtcs: List[str] = Field(default_factory=list, description="List of Diagnostic Trouble Codes")
    symptoms: List[str] = Field(default_factory=list, description="List of reported symptoms")
    photos: List[str] = Field(default_factory=list, description="List of photo URLs or identifiers")

class RankedCause(BaseModel):
    cause: str = Field(..., description="Description of the potential cause")
    probability: float = Field(..., description="Probability or confidence score of the cause")
    reasoning: str = Field(..., description="Reasoning for this cause")

class DiagnosisResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    ranked_causes: List[RankedCause] = Field(default_factory=list, description="Ranked list of potential causes")
    next_steps: List[str] = Field(default_factory=list, description="Recommended next diagnostic steps")

class SSEEventType(str, Enum):
    STEP = "step"
    EVIDENCE = "evidence"
    CONFIDENCE = "confidence"
    ESCALATION = "escalation"
    HEARTBEAT = "heartbeat"
    DONE = "done"

class SSEEvent(BaseModel):
    event: SSEEventType
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
