"""Request/response models for the interface contract frozen on 18 Sep (Section 6)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateDiagnosisResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobSnapshot(BaseModel):
    job_id: str
    status: str
    diagnosis: dict[str, Any] | None = None
    error: str | None = None


class DecisionIn(BaseModel):
    technician_id: str = Field(..., min_length=1, max_length=40)
    notes: str | None = Field(None, max_length=500)


class DecisionOut(BaseModel):
    job_id: str
    status: Literal["approved", "rejected"]


class FeedbackIn(BaseModel):
    confirmed_cause: str = Field(..., min_length=1, max_length=300)
    confirmed_fix: str = Field(..., min_length=1, max_length=1000)
    part_cost: float | None = Field(None, ge=0)
    labour_hours: float | None = Field(None, ge=0, le=100)


class FeedbackOut(BaseModel):
    job_id: str
    status: Literal["closed"] = "closed"
    knowledge_base: dict[str, int]
