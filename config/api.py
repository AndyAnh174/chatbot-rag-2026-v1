from ninja import NinjaAPI
from ninja.security import HttpBearer


class AuthBearer(HttpBearer):
    def authenticate(self, request, token: str):
        # TODO: replace with JWT validation
        if token == "dev-token":
            return token
        return None


api = NinjaAPI(
    title="Wellness Chatbot API",
    version="1.0.0",
    description="RAG-based student counseling chatbot (RTIC)",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Register app routers
from apps.chat.api import router as chat_router          # noqa: E402
from apps.ingestion.api import router as ingestion_router  # noqa: E402

api.add_router("/chat", chat_router, tags=["Chat"])
api.add_router("/ingest", ingestion_router, tags=["Ingestion"])
