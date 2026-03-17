from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import rewrite_node, retrieve_node, rerank_node, contextual_rewrite_node, generate_node


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("contextual_rewrite", contextual_rewrite_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "contextual_rewrite")
    graph.add_edge("contextual_rewrite", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


# Singleton graph instance
rag_graph = build_graph()
