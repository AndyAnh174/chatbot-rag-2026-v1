# Wellness Chatbot – Project Summary (RTIC × HCMUTE)

## Tổng quan
Chatbot AI tư vấn sinh viên, RAG pipeline nâng cao, do sinh viên CLB RTIC xây dựng trên hệ thống Wellness HCMUTE.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Web API | Django 5.1 + Django Ninja 1.6 |
| AI Orchestration | LangGraph (StateGraph) |
| LLM | GPT-4o-mini (gpt-4o-mini-2024-07-18) |
| Embedding + Rerank | Ollama `qllama/bge-reranker-v2-m3:latest` @ `http://222.253.80.30:11434` |
| Document Parser | Docling Serve v1.14.3 @ `http://222.253.80.30:5001` |
| Vector DB | Qdrant (self-hosted, `http://localhost:6333`) |
| Object Storage | MinIO (self-hosted, `localhost:9000`) |
| Queue / Cache | Redis (password: `dev_redis_pass_123`) |
| Task Queue | Celery 5.4 |
| DB | PostgreSQL (`localhost:5433`) |

---

## RAG Pipeline (5 nodes)

```
original_question
  -> rewrite_node              # Viet lai cau hoi + extract doc_type tu DB (GPT-4o-mini)
  -> retrieve_node             # Embed (Ollama BGE) -> Qdrant search voi metadata filter
  -> rerank_node               # BGE rerank song song (asyncio.gather) -> top 5
  -> contextual_rewrite_node   # Viet lai cau hoi ket hop context (GPT-4o-mini)
  -> generate_node             # Sinh cau tra loi (GPT-4o-mini)
  -> answer + sources
```

### State (AgentState TypedDict)
- session_id, original_question, rewritten_question, contextual_question
- messages, retrieved_docs, reranked_docs, answer, sources, metadata_filter

---

## Ingestion Pipeline (Celery task: process_document)

1. Download raw file tu MinIO (documents-raw)
2. CSV/TSV: parse truc tiep, bo qua Docling (group 10 rows/chunk)
3. PDF/DOCX/MD/image: gui Docling Serve async -> poll -> lay document.md_content
4. Strip anh base64 inline khoi markdown
5. Auto-classify doc_type bang GPT-4o-mini neu chua co (tra ve snake_case)
6. Luu parsed markdown vao MinIO (documents-parsed)
7. Chunk text (split double newline, min 100 / max 1000 chars)
8. Embed tung chunk (Ollama BGE) -> upsert Qdrant voi payload {text, source, doc_type, document_id, chunk_index}
9. Update IngestionJob.status = DONE

---

## API Endpoints

| Method | Path | Mo ta |
|--------|------|-------|
| POST | /api/chat/ | Chat (async) |
| GET | /api/chat/history/{session_id}/ | Lich su chat |
| POST | /api/ingest/ | Upload tai lieu |
| GET | /api/ingest/status/{job_id}/ | Trang thai ingestion job |
| GET | /api/ingest/documents/ | Danh sach tai lieu |
| DELETE | /api/ingest/documents/{document_id}/ | Xoa tai lieu (Qdrant + MinIO + DB) |
| GET | /test-ui/ | Test UI (upload + chat + CRUD) |

---

## Models

- Session: chat session (UUID pk)
- Message: role (user/assistant), content, sources (JSONField)
- Document: filename, doc_type, minio_path_raw, minio_path_parsed, content_type
- IngestionJob: document FK, status (queued/processing/done/failed), error

---

## Key Files

```
apps/
  chat/
    api.py          # chat + history endpoints
    services.py     # run_chat(), get_history() — wire LangGraph
  ingestion/
    api.py          # upload, status, list, delete endpoints
    services.py     # enqueue_ingestion(), delete_document()
    tasks.py        # Celery pipeline (Docling -> chunk -> embed -> Qdrant)
  rag/
    agent.py        # LangGraph graph build
    nodes.py        # 5 nodes: rewrite, retrieve, rerank, contextual_rewrite, generate
    prompts.py      # REWRITE_SYSTEM_TEMPLATE, CONTEXTUAL_REWRITE_SYSTEM, GENERATE_SYSTEM
    state.py        # AgentState TypedDict
config/
  settings/base.py  # settings chung
  .env.dev          # env vars cho dev
templates/
  test_ui.html      # Test UI (upload + chat + doc CRUD)
```

---

## Prompts

- GENERATE_SYSTEM: Wellness Chatbot cua HCMUTE, xay dung boi CLB RTIC. Tra loi dua tren tai lieu, khong bia dat, than thien, tieng Viet.
- REWRITE_SYSTEM_TEMPLATE: Viet lai cau hoi ro nghia + xac dinh doc_type tu danh sach dong lay tu DB. Output: QUESTION / DOCTYPE
- CONTEXTUAL_REWRITE_SYSTEM: Viet lai cau hoi ket hop context tu docs da rerank.

---

## Luu y quan trong

- Ollama retry: _ollama_post() retry 3 lan (3/6/9s) khi ConnectTimeout
- Rerank song song: asyncio.gather cho 10 docs cung luc
- Docling response field dung: result_data["document"]["md_content"]
- doc_type filter: Qdrant filter theo doc_type, fallback khong filter neu rong
- doc_types dong: lay tu DB moi lan rewrite, tu nhan loai moi khi upload
- Image trong PDF: bi strip ra, khong embed vao chunk
- MinIO buckets: documents-raw (file goc), documents-parsed (markdown sau Docling)
- Redis: can password dev_redis_pass_123 trong URL
- Celery: can restart thu cong sau khi sua tasks.py
