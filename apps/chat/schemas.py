from pydantic import BaseModel
from typing import List
from datetime import datetime
import uuid


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    message: str


class MessageSchema(BaseModel):
    role: str
    content: str
    sources: List[str] = []
    created_at: datetime


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    sources: List[str] = []


class ChatHistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: List[MessageSchema]
