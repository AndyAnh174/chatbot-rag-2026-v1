# Features — Chatbot Tư Vấn Wellness (RTIC)

## Core Features

### 1. Question Rewriting
- Nhận câu hỏi thô từ người dùng
- Tự động sửa lỗi chính tả, bổ sung ngữ cảnh từ lịch sử hội thoại
- Output: câu hỏi rõ nghĩa, đầy đủ context để truy vấn chính xác hơn

### 2. Metadata-Aware Retrieval
- Sinh câu truy vấn kết hợp với metadata filter (loại tài liệu, ngành, năm...)
- Tìm kiếm semantic trên Qdrant vector database
- Trả về top-K documents liên quan nhất

### 3. Reranking
- Dùng `qllama/bge-reranker-v2-m3:latest` (Ollama) để xếp hạng lại kết quả
- Loại bỏ các đoạn ít liên quan, giữ lại context chất lượng cao nhất
- Giảm hallucination, tăng độ chính xác câu trả lời

### 4. RAG Generation
- Ghép câu hỏi đã rewrite + docs đã rerank vào prompt
- GPT-4o-mini tổng hợp thành câu trả lời tự nhiên, mạch lạc
- Có thể stream response

### 5. Multi-turn Conversation
- Lưu lịch sử hội thoại theo session
- Rewrite step dùng lịch sử để hiểu câu hỏi trong ngữ cảnh liên tục

---

## Document Ingestion Pipeline

### Supported Formats
- PDF, DOCX, Markdown

### Pipeline
1. **Parse** — LlamaParse trích xuất text từ file
2. **Chunk** — Chia nhỏ theo đoạn, giữ nguyên ngữ nghĩa
3. **Embed** — Tạo vector embedding bằng BGE model (Ollama)
4. **Index** — Lưu vào Qdrant kèm metadata (nguồn, loại tài liệu, ngành...)

---

## API Endpoints (Django Ninja)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/chat/` | Gửi câu hỏi, nhận câu trả lời |
| POST | `/api/chat/stream/` | Streaming response |
| POST | `/api/ingest/` | Upload & index tài liệu mới |
| GET | `/api/chat/history/{session_id}/` | Lấy lịch sử hội thoại |

---

## Knowledge Base

| Tài liệu | Use case |
|----------|----------|
| Sổ tay sinh viên | Tư vấn quy chế, học vụ, tín chỉ |
| CTĐT các ngành | Tư vấn tuyển sinh, chương trình học, định hướng nghề |
| QĐ đổi tên trường | Thông tin pháp lý, tên chính thức |
| QĐ điều chỉnh nhân sự | Cơ cấu tổ chức, phòng ban |
