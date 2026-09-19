from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The exact prompt sent to the AI system.")
    response: str = Field(..., min_length=1, description="The exact AI response returned for the prompt.")


class AskResponse(BaseModel):
    receipt_id: str
    sequence_no: int
    prompt: str
    response: str
    previous_hash: str
    current_hash: str
    timestamp: str


class VerifyRequest(BaseModel):
    receipt_id: str = Field(..., min_length=1, description="Receipt identifier to verify.")


class VerifyResponse(BaseModel):
    receipt_id: str
    valid: bool
    status: str
    message: str
    stored_hash: str | None = None
    calculated_hash: str | None = None
    explanation: str


class TamperResponse(BaseModel):
    receipt_id: str
    status: str
    message: str
