# Tech Stack — Chatbot Tư Vấn Wellness (RTIC)

## Backend

| Thành phần | Công nghệ | Ghi chú |
|-----------|-----------|---------|
| Web framework | **Django Ninja** | Async REST API, auto OpenAPI docs |
| AI orchestration | **LangGraph** | Quản lý agent flow dạng state machine |
| LLM | **OpenAI GPT-4o-mini** | Sinh câu trả lời cuối cùng — external API |
| Embedding | `qllama/bge-reranker-v2-m3:latest` | Ollama — external API |
| Reranker | `qllama/bge-reranker-v2-m3:latest` | Ollama — external API |
| Document parser | **Docling Serve v1.14.3** | Self-hosted, GPU-accelerated, thay thế LlamaParse |

## Self-hosted Infrastructure

> Tất cả services dưới đây đều tự host, không phụ thuộc cloud vendor.

| Service | Mục đích | Ghi chú |
|---------|----------|---------|
| **PostgreSQL** | Relational database — lưu user, session, chat history, metadata | Self-hosted |
| **Qdrant** | Vector database — lưu embedding, tìm kiếm semantic | Self-hosted |
| **MinIO** | Object storage — lưu file gốc (PDF, DOCX...) sau khi upload | Self-hosted |
| **Redis** | Cache, session, task queue (Celery hoặc Django Q) | Self-hosted |
| **Docling Serve** | Document parsing API (PDF, DOCX, PPTX, HTML...) | Self-hosted, `http://222.253.80.30:5001/` |

## External APIs

| Service | Mục đích |
|---------|----------|
| **Ollama** (`http://222.253.80.30:11434/`) | Embedding + Reranking |
| **OpenAI API** | LLM generation (GPT-4o-mini) |

## MinIO Buckets

| Bucket | Mục đích |
|--------|----------|
| `documents-raw` | File gốc upload lên (PDF, DOCX, Markdown) trước khi parse |
| `documents-parsed` | Text đã extract từ LlamaParse (JSON/Markdown) |

> Tạo bucket khi khởi tạo hệ thống:
> ```bash
> mc alias set local http://localhost:9000 MINIO_ROOT_USER MINIO_ROOT_PASSWORD
> mc mb local/documents-raw
> mc mb local/documents-parsed
> ```

## Docling Serve API

**Base URL:** `http://222.253.80.30:5001`
**Version:** docling-serve 1.14.3 / docling 2.76.0

### Endpoints chính

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/health` | Kiểm tra server còn sống |
| GET | `/ready` | Kiểm tra server sẵn sàng nhận request |
| GET | `/version` | Thông tin version |
| POST | `/v1/convert/file` | Parse file sync (upload trực tiếp) |
| POST | `/v1/convert/source` | Parse từ URL sync |
| POST | `/v1/convert/file/async` | Parse file async → trả `task_id` |
| POST | `/v1/convert/source/async` | Parse URL async → trả `task_id` |
| GET | `/v1/status/poll/{task_id}` | Kiểm tra trạng thái task async |
| GET | `/v1/result/{task_id}` | Lấy kết quả task async |
| POST | `/v1/chunk/hybrid/file` | Parse + chunk hybrid sync |
| POST | `/v1/chunk/hybrid/file/async` | Parse + chunk hybrid async |
| POST | `/v1/chunk/hierarchical/file` | Parse + chunk hierarchical sync |

### Ví dụ sử dụng

```bash
# Health check
curl http://222.253.80.30:5001/health

# Parse file sync
curl -X POST http://222.253.80.30:5001/v1/convert/file \
  -F "files=@document.pdf"

# Parse file async
curl -X POST http://222.253.80.30:5001/v1/convert/file/async \
  -F "files=@document.pdf"
# → {"task_id": "abc123"}

# Poll status
curl http://222.253.80.30:5001/v1/status/poll/abc123

# Lấy kết quả
curl http://222.253.80.30:5001/v1/result/abc123
```

```python
# Python (httpx)
import httpx

async def parse_document(file_path: str) -> dict:
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            # Gửi async, lấy task_id
            resp = await client.post(
                "http://222.253.80.30:5001/v1/convert/file/async",
                files={"files": f}
            )
        task_id = resp.json()["task_id"]

        # Poll đến khi xong
        while True:
            status = await client.get(
                f"http://222.253.80.30:5001/v1/status/poll/{task_id}"
            )
            if status.json()["status"] == "success":
                break

        result = await client.get(
            f"http://222.253.80.30:5001/v1/result/{task_id}"
        )
        return result.json()
```

> **Lưu ý:** Dùng `/async` endpoints trong Celery worker để tránh timeout khi parse file lớn.

## Dependencies (Python)

```
django
django-ninja
psycopg[binary]     # PostgreSQL driver
langgraph
langchain
langchain-openai
langchain-qdrant
qdrant-client
openai
httpx
minio
redis
django-redis
celery
```

## Architecture Diagram

```
                        ┌─────────────────────────────────┐
                        │         Django Ninja API         │
                        │   /api/chat/    /api/ingest/     │
                        └──────────┬──────────┬────────────┘
                                   │          │
                     ┌─────────────▼──┐  ┌────▼──────────────┐
                     │  LangGraph     │  │  Ingestion Worker  │
                     │  RAG Agent     │  │  (Celery/async)    │
                     └──┬────┬────┬───┘  └──┬────────┬────────┘
                        │    │    │          │        │
               ┌────────▼┐ ┌─▼──┐ │      ┌──▼──┐  ┌──▼──────┐
               │  OpenAI │ │Qdrant│ │      │MinIO│  │LlamaParse│
               │GPT-4o   │ │Vector│ │      │ S3  │  │ Parser  │
               └─────────┘ └──▲──┘ │      └─────┘  └─────────┘
                              │    │
                           ┌──▼──┐ │
                           │Ollama│ │     ┌──────────┐
                           │ BGE │ │     │  Redis   │
                           └─────┘ │     │ Cache/Q  │
                                   │     └──────────┘
                                   │
                              External APIs
```

## Data Flow

### Chat Flow
1. User gửi câu hỏi → Django Ninja nhận request
2. Kiểm tra Redis cache (nếu câu hỏi đã có kết quả)
3. LangGraph khởi chạy agent graph
4. **Rewrite node**: GPT-4o-mini rewrite câu hỏi với chat history
5. **Query node**: Sinh metadata filter + embedding query (Ollama)
6. **Retrieve node**: Qdrant trả top-K docs
7. **Rerank node**: Ollama BGE reranker sắp xếp lại
8. **Generate node**: GPT-4o-mini sinh answer từ docs + question
9. Lưu kết quả vào Redis, trả response về user

### Ingestion Flow
1. User upload file → Django Ninja nhận
2. **Lưu file gốc** vào MinIO bucket `documents-raw`
3. Đẩy task vào Celery queue (Redis làm broker)
4. Worker xử lý: LlamaParse trích xuất text
5. **Lưu text đã parse** vào MinIO bucket `documents-parsed`
6. Chunk text → Ollama BGE tạo embedding
7. Index vào Qdrant kèm metadata (nguồn, loại tài liệu, ngành...)
