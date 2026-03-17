from typing import TypedDict, List, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    session_id: str
    original_question: str
    rewritten_question: str
    messages: Annotated[List[BaseMessage], operator.add]
    retrieved_docs: List[dict]
    reranked_docs: List[dict]
    answer: str
    sources: List[str]
    metadata_filter: Optional[dict]
    contextual_question: str
