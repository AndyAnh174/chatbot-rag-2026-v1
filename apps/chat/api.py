from ninja import Router
from .schemas import ChatRequest, ChatResponse, ChatHistoryResponse
import uuid

router = Router()


@router.post("/", response=ChatResponse)
async def chat(request, payload: ChatRequest):
    from .services import run_chat
    return await run_chat(payload)


@router.get("/history/{session_id}/", response=ChatHistoryResponse)
async def chat_history(request, session_id: uuid.UUID):
    from .services import get_history
    return await get_history(str(session_id))
