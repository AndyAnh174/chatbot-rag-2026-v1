import asyncio
import logging

import httpx
import numpy as np
from django.conf import settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from .prompts import CONTEXTUAL_REWRITE_SYSTEM, GENERATE_SYSTEM, REWRITE_SYSTEM_TEMPLATE
from .state import AgentState

logger = logging.getLogger(__name__)

TOP_K_RETRIEVE = 10
TOP_K_RERANK = 5
OLLAMA_TIMEOUT = 120  # seconds — tăng để tránh timeout khi Ollama bận
OLLAMA_RETRIES = 3

_NONE_VALUES = {"none", "unknown", "", "null", "không xác định"}


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
    )


async def _ollama_post(payload: dict) -> dict:
    """POST to Ollama /api/embed với retry khi timeout."""
    last_exc = None
    for attempt in range(1, OLLAMA_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embed",
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < OLLAMA_RETRIES:
                wait = attempt * 3
                logger.warning("Ollama timeout (attempt %d/%d), retry in %ds", attempt, OLLAMA_RETRIES, wait)
                await asyncio.sleep(wait)
    raise last_exc


async def _embed(text: str) -> list[float]:
    """Call Ollama /api/embed, return embedding vector."""
    data = await _ollama_post({"model": settings.OLLAMA_EMBED_MODEL, "input": text})
    return data["embeddings"][0]


async def _rerank_score(query: str, doc_text: str) -> float:
    """
    BGE cross-encoder reranker via Ollama /api/embed.
    Compute cosine similarity between query embedding and doc embedding.
    """
    data = await _ollama_post({"model": settings.OLLAMA_RERANK_MODEL, "input": [query, doc_text]})
    embeddings = data["embeddings"]
    q_vec = np.array(embeddings[0])
    d_vec = np.array(embeddings[1])
    score = float(np.dot(q_vec, d_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec) + 1e-9))
    return score


def _parse_rewrite_response(text: str) -> tuple[str, str | None]:
    """Parse QUESTION/DOCTYPE từ response của rewrite_node."""
    question = ""
    doc_type = None
    for line in text.strip().splitlines():
        if line.startswith("QUESTION:"):
            question = line[len("QUESTION:"):].strip()
        elif line.startswith("DOCTYPE:"):
            raw = line[len("DOCTYPE:"):].strip().lower()
            if raw not in _NONE_VALUES:
                doc_type = raw
    return question or text.strip(), doc_type


async def _get_available_doc_types() -> str:
    """Lấy danh sách doc_types hiện có trong DB."""
    from apps.ingestion.models import Document
    doc_types = [
        dt async for dt in
        Document.objects.values_list("doc_type", flat=True).distinct().exclude(doc_type="")
    ]
    if not doc_types:
        return "- (chưa có tài liệu nào)"
    return "\n".join(f"- {dt}" for dt in sorted(set(doc_types)))


async def rewrite_node(state: AgentState) -> AgentState:
    """Rewrite câu hỏi và extract metadata filter (doc_type) động từ DB."""
    logger.debug("rewrite_node: original=%s", state["original_question"])

    doc_types_list = await _get_available_doc_types()
    system_prompt = REWRITE_SYSTEM_TEMPLATE.format(doc_types_list=doc_types_list)

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(state["messages"])
    messages.append(HumanMessage(content=state["original_question"]))

    llm = _get_llm()
    response = await llm.ainvoke(messages)
    rewritten, doc_type = _parse_rewrite_response(response.content)

    metadata_filter = None
    if doc_type:
        metadata_filter = {"doc_type": doc_type}

    logger.debug("rewrite_node: rewritten=%s doc_type=%s", rewritten, doc_type)
    return {**state, "rewritten_question": rewritten, "metadata_filter": metadata_filter}


async def retrieve_node(state: AgentState) -> AgentState:
    """Embed câu hỏi và tìm kiếm Qdrant với metadata filter."""
    question = state["rewritten_question"] or state["original_question"]
    metadata_filter = state.get("metadata_filter")
    logger.debug("retrieve_node: query=%s filter=%s", question, metadata_filter)

    vector = await _embed(question)

    qdrant_filter = None
    if metadata_filter and metadata_filter.get("doc_type"):
        qdrant_filter = Filter(
            must=[FieldCondition(key="doc_type", match=MatchValue(value=metadata_filter["doc_type"]))]
        )

    qdrant = QdrantClient(url=settings.QDRANT_URL)
    results = qdrant.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=vector,
        limit=TOP_K_RETRIEVE,
        with_payload=True,
        query_filter=qdrant_filter,
    )

    # Fallback: nếu filter quá chặt trả về rỗng, thử lại không filter
    if not results and qdrant_filter:
        logger.debug("retrieve_node: no results with filter, retrying without filter")
        results = qdrant.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=TOP_K_RETRIEVE,
            with_payload=True,
        )

    retrieved_docs = [
        {
            "text": hit.payload.get("text", ""),
            "source": hit.payload.get("source", ""),
            "doc_type": hit.payload.get("doc_type", ""),
            "score": hit.score,
        }
        for hit in results
    ]

    logger.debug("retrieve_node: found %d docs", len(retrieved_docs))
    return {**state, "retrieved_docs": retrieved_docs}


async def rerank_node(state: AgentState) -> AgentState:
    """Rerank retrieved docs bằng Ollama BGE Reranker."""
    docs = state["retrieved_docs"]
    if not docs:
        return {**state, "reranked_docs": []}

    question = state["rewritten_question"] or state["original_question"]
    logger.debug("rerank_node: reranking %d docs", len(docs))

    scores = await asyncio.gather(*[_rerank_score(question, doc["text"]) for doc in docs])
    scored = [{**doc, "rerank_score": score} for doc, score in zip(docs, scores)]

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    reranked = scored[:TOP_K_RERANK]

    logger.debug("rerank_node: kept %d docs after rerank", len(reranked))
    return {**state, "reranked_docs": reranked}


async def contextual_rewrite_node(state: AgentState) -> AgentState:
    """Rewrite lần 2: kết hợp câu hỏi với context từ docs đã rerank."""
    docs = state["reranked_docs"]
    question = state["rewritten_question"] or state["original_question"]

    if not docs:
        return {**state, "contextual_question": question}

    context = "\n\n".join(f"[{i + 1}] {doc['text']}" for i, doc in enumerate(docs))

    system_msg = SystemMessage(content=CONTEXTUAL_REWRITE_SYSTEM.format(context=context))
    human_msg = HumanMessage(content=question)

    llm = _get_llm()
    response = await llm.ainvoke([system_msg, human_msg])
    contextual_question = response.content.strip()

    logger.debug("contextual_rewrite_node: contextual_question=%s", contextual_question)
    return {**state, "contextual_question": contextual_question}


async def generate_node(state: AgentState) -> AgentState:
    """Tổng hợp câu trả lời từ docs đã rerank, dùng contextual_question."""
    docs = state["reranked_docs"]
    question = state.get("contextual_question") or state["rewritten_question"] or state["original_question"]

    if not docs:
        return {
            **state,
            "answer": "Xin lỗi, tôi không tìm thấy thông tin liên quan trong tài liệu. Vui lòng thử câu hỏi khác.",
            "sources": [],
        }

    context = "\n\n".join(f"[{i + 1}] {doc['text']}" for i, doc in enumerate(docs))
    sources = list({doc["source"] for doc in docs if doc.get("source")})

    system_msg = SystemMessage(content=GENERATE_SYSTEM.format(context=context))
    human_msg = HumanMessage(content=question)

    llm = _get_llm()
    response = await llm.ainvoke([system_msg, human_msg])
    answer = response.content.strip()

    logger.debug("generate_node: answer length=%d sources=%s", len(answer), sources)
    return {**state, "answer": answer, "sources": sources}
