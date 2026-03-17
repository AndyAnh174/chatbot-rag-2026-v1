# Thông Tin Dự Án: Chatbot Tư Vấn Wellness (RTIC)

## Tổng Quan

Chatbot AI hỗ trợ tư vấn sinh viên, sử dụng kiến trúc RAG (Retrieval-Augmented Generation) nâng cao với pipeline rewrite → metadata query → rerank → answer.

---

## Luồng Hoạt Động (Flow)

```
[User Question]
      │
      ▼
[1. Rewrite] — Viết lại câu hỏi: sửa lỗi chính tả, bổ sung ngữ cảnh từ lịch sử chat
      │
      ▼
[2. Metadata Query] — Sinh câu truy vấn + metadata filter để tìm kiếm trong Qdrant
      │
      ▼
[3. Retrieve] — Truy xuất top-K documents từ vector database
      │
      ▼
[4. Rerank] — Xếp hạng lại documents bằng BGE Reranker, chọn đoạn liên quan nhất
      │
      ▼
[5. Generation] — Đưa câu hỏi + docs vào prompt, LLM tổng hợp câu trả lời tự nhiên
      │
      ▼
[Answer] — Trả kết quả cho người dùng
```

---

## Knowledge Base (Dữ Liệu Nền Tảng)

| Tài liệu | Nội dung |
|----------|----------|
| **Sổ tay sinh viên** | Quy chế học vụ, thông tin tín chỉ, nội quy |
| **CTĐT các ngành** | Chương trình đào tạo, môn học, định hướng nghề nghiệp — dữ liệu cốt lõi cho tư vấn tuyển sinh |
| **QĐ đổi tên trường** | Thông tin pháp lý, lịch sử, tên gọi chính thức mới nhất |
| **QĐ điều chỉnh nhân sự** | Cơ cấu tổ chức, phòng ban hiện tại |

Định dạng tài liệu hỗ trợ: **PDF, Markdown, DOCX** (xử lý qua LlamaParse).

---

## Tech Stack

### Backend
| Thành phần | Công nghệ |
|-----------|-----------|
| Web framework | **Django Ninja** (async REST API) |
| AI orchestration | **LangGraph** (agent flow, state machine) |
| LLM | **OpenAI GPT-4o-mini** |
| Embedding | `qllama/bge-reranker-v2-m3:latest` via Ollama |
| Reranker | `qllama/bge-reranker-v2-m3:latest` via Ollama |
| Vector DB | **Qdrant** |
| Document parser | **LlamaParse** (PDF, DOCX, Markdown, CSV, TSV) |

### Infrastructure
| Thành phần | Chi tiết |
|-----------|----------|
| Ollama server | `http://222.253.80.30:11434/` |
| Vector DB | Qdrant (self-hosted) |

---

## Features

### Core
- **Question Rewriting**: Tự động rewrite câu hỏi với context từ lịch sử chat
- **Hybrid Retrieval**: Metadata filtering + semantic search trên Qdrant
- **Reranking**: BGE Reranker v2 M3 sắp xếp lại kết quả để tăng độ chính xác
- **RAG Generation**: GPT-4o-mini tổng hợp câu trả lời từ retrieved docs
- **Multi-turn Chat**: Lưu lịch sử hội thoại để rewrite có ngữ cảnh

### Document Ingestion
- Parse PDF/DOCX/Markdown bằng LlamaParse
- Chunking + embedding + index vào Qdrant
- Metadata tagging (loại tài liệu, ngành, năm học...)

### API
- REST API via Django Ninja
- Endpoint chat (stream hoặc full response)
- Endpoint ingest tài liệu mới
