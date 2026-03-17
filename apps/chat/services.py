import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from .models import Message, Session
from .schemas import ChatHistoryResponse, ChatRequest, ChatResponse, MessageSchema

logger = logging.getLogger(__name__)


async def run_chat(payload: ChatRequest) -> ChatResponse:
    from apps.rag.agent import rag_graph

    # Get or create session
    session, created = await Session.objects.aget_or_create(id=payload.session_id)
    if created:
        logger.info("New session created: %s", session.id)

    # Load chat history as LangChain messages
    history = []
    async for msg in session.messages.all():
        if msg.role == Message.Role.USER:
            history.append(HumanMessage(content=msg.content))
        else:
            history.append(AIMessage(content=msg.content))

    # Run LangGraph RAG pipeline
    result = await rag_graph.ainvoke({
        "session_id": str(payload.session_id),
        "original_question": payload.message,
        "rewritten_question": "",
        "messages": history,
        "retrieved_docs": [],
        "reranked_docs": [],
        "answer": "",
        "sources": [],
        "metadata_filter": None,
        "contextual_question": "",
    })

    # Persist messages to DB
    await Message.objects.acreate(
        session=session,
        role=Message.Role.USER,
        content=payload.message,
    )
    await Message.objects.acreate(
        session=session,
        role=Message.Role.ASSISTANT,
        content=result["answer"],
        sources=result["sources"],
    )

    logger.info("Chat complete session=%s answer_len=%d", session.id, len(result["answer"]))
    return ChatResponse(
        session_id=payload.session_id,
        answer=result["answer"],
        sources=result["sources"],
    )


async def get_history(session_id: uuid.UUID) -> ChatHistoryResponse:
    session = await Session.objects.aget(id=session_id)
    messages = [
        MessageSchema(
            role=msg.role,
            content=msg.content,
            sources=msg.sources,
            created_at=msg.created_at,
        )
        async for msg in session.messages.all()
    ]
    return ChatHistoryResponse(session_id=session_id, messages=messages)
