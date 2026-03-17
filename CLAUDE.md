# chatbot-wellness

Chatbot AI tư vấn sinh viên (RTIC) — kiến trúc RAG nâng cao với pipeline: rewrite → metadata query → rerank → generate.

## Project Docs

- [Thông tin dự án & flow](docs/information.md)
- [Features](docs/feature.md)
- [Tech stack](docs/tech-stack.md)

## Tech Stack

| Layer | Technology | Host |
|-------|-----------|------|
| Web API | Django Ninja | — |
| AI orchestration | LangGraph | — |
| LLM | OpenAI GPT-4o-mini | External API |
| Embedding & Reranker | `qllama/bge-reranker-v2-m3:latest` (Ollama) | External: `http://222.253.80.30:11434/` |
| Database | PostgreSQL | **Self-hosted** |
| Vector DB | Qdrant | **Self-hosted** |
| Object storage | MinIO | **Self-hosted** |
| Cache / Queue broker | Redis | **Self-hosted** |
| Document parser | Docling Serve v1.14.3 | **Self-hosted**: `http://222.253.80.30:5001/` |

## RAG Flow

```
Question → Rewrite → Metadata Query → Retrieve (Qdrant) → Rerank (BGE) → Generate (GPT-4o-mini) → Answer
```

## Knowledge Base

- Sổ tay sinh viên
- CTĐT các ngành (cốt lõi tư vấn tuyển sinh)
- QĐ đổi tên trường
- QĐ điều chỉnh nhân sự

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start infrastructure (dev)
docker compose -f docker-compose.dev.yml up -d

# Run dev server (local, không dùng Docker)
python manage.py migrate
python manage.py runserver

# Run tests
pytest

# Lint & format
ruff check .
ruff format .
```

## Code Conventions

### Architecture rules
- **NinjaAPI singleton** sống ở `config/api.py` — KHÔNG tạo NinjaAPI mới trong apps
- **Router only** trong mỗi app (`ninja.Router`), mount vào `config/api.py`
- **Business logic** trong `services.py`, KHÔNG viết logic trong `api.py`
- **Celery tasks** trong `tasks.py`, KHÔNG gọi blocking I/O trực tiếp trong Django view
- **LangGraph nodes** trong `apps/rag/nodes.py`, graph build trong `apps/rag/agent.py`
- **AgentState** là TypedDict duy nhất truyền qua graph — KHÔNG dùng dict thô

### Django / API
- Dùng **async views** (`async def`) cho chat endpoints — sync cho ingestion upload (Celery lo phần nặng)
- Settings đọc từ env qua `django-environ` trong `base.py` — KHÔNG hardcode giá trị
- KHÔNG import trực tiếp `settings` trong apps, truyền qua `django.conf.settings`
- Migration luôn được commit cùng model changes

### Naming
- App models: `PascalCase` (e.g., `IngestionJob`)
- API schemas (Pydantic): `PascalCase` + suffix `Request`/`Response`
- Celery tasks: `snake_case`, decorator `@shared_task`
- LangGraph nodes: `snake_case` + suffix `_node` (e.g., `rewrite_node`)

### External services
- Gọi Docling/Ollama/Qdrant qua `httpx.AsyncClient` — KHÔNG dùng `requests`
- URL lấy từ `django.conf.settings`, KHÔNG hardcode
- Docling: luôn dùng `/async` endpoints trong Celery worker
- MinIO: dùng `sync_to_async` hoặc chạy trong Celery task (SDK là sync)

### Linting
- `ruff check .` — phải pass trước khi commit
- `ruff format .` — format tự động
- Config trong `pyproject.toml`

## Environment Variables

```
# External APIs
OPENAI_API_KEY=                        # GPT-4o-mini
OLLAMA_BASE_URL=http://222.253.80.30:11434/
DOCLING_BASE_URL=http://222.253.80.30:5001  # Docling Serve (self-hosted)

# Self-hosted services
QDRANT_URL=                            # Qdrant endpoint (self-hosted)
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET_RAW=documents-raw
MINIO_BUCKET_PARSED=documents-parsed

# Django
DATABASE_URL=postgresql://user:pass@localhost:5432/chatbot_wellness
```

## Project Structure (dự kiến)

```
chatbot-wellness/
├── apps/
│   ├── chat/           # Chat API endpoints (Django Ninja)
│   ├── ingestion/      # Document ingestion pipeline + Celery tasks
│   └── rag/            # LangGraph agent, rewrite, rerank
├── docs/               # Project documentation
├── manage.py
└── requirements.txt
```

## MinIO Buckets

| Bucket | Mục đích |
|--------|----------|
| `documents-raw` | File gốc upload (PDF, DOCX, Markdown) |
| `documents-parsed` | Text đã extract từ LlamaParse |

Khởi tạo bucket:
```bash
mc alias set local http://localhost:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
mc mb local/documents-raw
mc mb local/documents-parsed
```

## Gotchas

- Ollama dùng model `qllama/bge-reranker-v2-m3:latest` cho cả embedding lẫn rerank — cần pull model trên server `222.253.80.30` trước khi chạy.
- LangGraph state cần serialize được để lưu lịch sử multi-turn.
- Docling Serve chạy tại `http://222.253.80.30:5001/` — dùng `/v1/convert/file/async` trong Celery worker, tránh timeout với file lớn.
- MinIO cần tạo 2 bucket (`documents-raw`, `documents-parsed`) trước khi chạy ingestion.
- Redis vừa làm cache chat vừa làm Celery broker — cần đảm bảo Redis up trước khi start worker.
