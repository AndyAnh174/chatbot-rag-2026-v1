import uuid
from typing import Optional
from pydantic import BaseModel


class IngestionResponse(BaseModel):
    job_id: uuid.UUID
    document_id: uuid.UUID
    status: str  # queued | processing | done | failed


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    error: str = ""


class DocumentSchema(BaseModel):
    id: uuid.UUID
    filename: str
    doc_type: str
    content_type: str
    created_at: str
    job_status: Optional[str] = None
    job_error: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentSchema]
    total: int


class DeleteResponse(BaseModel):
    document_id: uuid.UUID
    deleted: bool
    message: str
