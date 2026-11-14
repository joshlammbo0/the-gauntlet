"""Pydantic schemas validating model outputs. Invalid output → treated as None (fallback to deterministic)."""
from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError, confloat


class ComponentJudgment(BaseModel):
    id: str
    present: bool
    evidence: Optional[str] = None


class MisconceptionJudgment(BaseModel):
    id: str
    present: bool
    evidence: Optional[str] = None


class TechnicalEvaluation(BaseModel):
    components: List[ComponentJudgment] = Field(default_factory=list)
    misconceptions: List[MisconceptionJudgment] = Field(default_factory=list)
    answered_question: bool = True
    correctness: confloat(ge=0, le=1) = 0.5
    depth: confloat(ge=0, le=1) = 0.5
    clarity: confloat(ge=0, le=1) = 0.5
    key_error: Optional[str] = None
    stronger_answer: Optional[str] = None
    notes: Optional[str] = None


class BehavioralEvaluation(BaseModel):
    answered_question: bool = True
    relevance: confloat(ge=0, le=1) = 0.5
    structure: confloat(ge=0, le=1) = 0.5
    specificity: confloat(ge=0, le=1) = 0.5
    ownership: confloat(ge=0, le=1) = 0.5
    authenticity: confloat(ge=0, le=1) = 0.5
    concision: confloat(ge=0, le=1) = 0.5
    reflection: confloat(ge=0, le=1) = 0.5
    unsupported_claims: List[str] = Field(default_factory=list)
    generic_phrases: List[str] = Field(default_factory=list)
    key_weakness: Optional[str] = None
    stronger_version: Optional[str] = None
    notes: Optional[str] = None


class InterviewerTurn(BaseModel):
    utterance: str
    intent: str = "ask"
    notes: Optional[str] = None


def parse(model_cls, data):
    if data is None:
        return None
    try:
        return model_cls(**data)
    except (ValidationError, TypeError):
        return None
