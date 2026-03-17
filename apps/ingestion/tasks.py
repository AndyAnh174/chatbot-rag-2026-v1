import csv
import io
import logging
import re
import time
import uuid

import httpx
from celery import shared_task
from django.conf import settings
from minio import Minio
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = logging.getLogger(__name__)

CHUNK_MIN = 100
CHUNK_MAX = 1000
CSV_ROWS_PER_CHUNK = 10  # group rows into chunks of this size
TOP_K_RETRIEVE = 10
DOCLING_POLL_INTERVAL = 2  # seconds
DOCLING_TIMEOUT = 180  # seconds


def _get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


def _parse_csv_tsv(file_bytes: bytes, filename: str) -> str:
    """Convert CSV/TSV to readable text, grouping rows for embedding."""
    delimiter = "\t" if filename.lower().endswith(".tsv") else ","
    text = file_bytes.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ""

    # Format each row as "col1: val1 | col2: val2 ..."
    formatted_rows = []
    for row in rows:
        parts = [f"{k.strip()}: {v.strip()}" for k, v in row.items() if v and v.strip()]
        formatted_rows.append(" | ".join(parts))

    # Group CSV_ROWS_PER_CHUNK rows into one chunk
    chunks = []
    for i in range(0, len(formatted_rows), CSV_ROWS_PER_CHUNK):
        group = formatted_rows[i : i + CSV_ROWS_PER_CHUNK]
        chunks.append("\n".join(group))

    return "\n\n".join(chunks)


def _chunk_text(text: str) -> list[str]:
    """Split text by double newlines, filter by length."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < CHUNK_MAX:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if len(current) >= CHUNK_MIN:
                chunks.append(current)
            current = para
    if len(current) >= CHUNK_MIN:
        chunks.append(current)
    return chunks


def _embed_text(text: str) -> list[float]:
    """Call Ollama /api/embed and return embedding vector."""
    resp = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/embed",
        json={"model": settings.OLLAMA_EMBED_MODEL, "input": text},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    # Ollama returns {"embeddings": [[...]], ...}
    return data["embeddings"][0]


_IMAGE_PATTERN = re.compile(r"!\[(?:[^\]]*)\]\(data:image/[^)]+\)")


def _strip_embedded_images(markdown_text: str) -> str:
    """Xóa các ảnh base64 inline khỏi markdown để tránh làm nặng embedding."""
    return _IMAGE_PATTERN.sub("", markdown_text)


def _classify_doc_type(text: str, filename: str) -> str:
    """Dùng LLM tự động phân loại loại tài liệu từ tên file + nội dung."""
    sample = text[:1500]
    prompt = (
        f"Dựa vào tên file và nội dung tài liệu bên dưới, hãy xác định loại tài liệu.\n"
        f"Trả về MỘT nhãn ngắn gọn dạng snake_case không dấu (ví dụ: sotay, ctdt, lich_hoc, thong_bao, quy_che, qd_nhansu...).\n"
        f"Chỉ trả về nhãn duy nhất, không giải thích.\n\n"
        f"Tên file: {filename}\n\nNội dung:\n{sample}"
    )
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": settings.OPENAI_LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 20,
        },
        timeout=30,
    )
    resp.raise_for_status()
    label = resp.json()["choices"][0]["message"]["content"].strip().lower()
    label = re.sub(r"[^a-z0-9_]", "_", label)[:32].strip("_")
    return label or "unknown"


def _ensure_collection(client: QdrantClient, vector_size: int):
    """Create Qdrant collection if it doesn't exist."""
    existing = [c.name for c in client.get_collections().collections]
    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", settings.QDRANT_COLLECTION)


@shared_task(bind=True, queue="ingestion", max_retries=3, default_retry_delay=30)
def process_document(self, job_id: str, document_id: str):
    """
    Full ingestion pipeline:
    1. Download raw file from MinIO
    2. Parse via Docling Serve (async)
    3. Save parsed markdown to MinIO
    4. Chunk → embed (Ollama) → upsert to Qdrant
    5. Update IngestionJob status
    """
    from .models import Document, IngestionJob

    job = IngestionJob.objects.get(id=job_id)
    doc = Document.objects.get(id=document_id)

    try:
        # ── Step 1: Update status ──────────────────────────────────────────
        job.status = IngestionJob.Status.PROCESSING
        job.save(update_fields=["status", "updated_at"])
        logger.info("Processing job_id=%s file=%s", job_id, doc.filename)

        # ── Step 2: Download raw file from MinIO ──────────────────────────
        minio = _get_minio_client()
        response = minio.get_object(settings.MINIO_BUCKET_RAW, doc.minio_path_raw)
        file_bytes = response.read()
        response.close()
        response.release_conn()
        logger.info("Downloaded %s bytes from MinIO", len(file_bytes))

        # ── Step 3: Parse document ────────────────────────────────────────
        fname_lower = doc.filename.lower()
        if fname_lower.endswith(".csv") or fname_lower.endswith(".tsv"):
            # CSV/TSV: parse directly, skip Docling
            markdown_text = _parse_csv_tsv(file_bytes, doc.filename)
            logger.info("Parsed CSV/TSV directly: %d chars", len(markdown_text))
        else:
            # PDF/DOCX/MD/etc: send to Docling Serve async
            with httpx.Client(timeout=30) as client:
                parse_resp = client.post(
                    f"{settings.DOCLING_BASE_URL}/v1/convert/file/async",
                    files={"files": (doc.filename, io.BytesIO(file_bytes), doc.content_type)},
                )
                parse_resp.raise_for_status()
                task_id = parse_resp.json()["task_id"]
                logger.info("Docling task_id=%s", task_id)

            # ── Step 4: Poll Docling until done ───────────────────────────
            elapsed = 0
            with httpx.Client(timeout=10) as client:
                while elapsed < DOCLING_TIMEOUT:
                    status_resp = client.get(
                        f"{settings.DOCLING_BASE_URL}/v1/status/poll/{task_id}"
                    )
                    status_resp.raise_for_status()
                    status_data = status_resp.json()
                    status = status_data.get("status") or status_data.get("task_status", "")
                    logger.debug("Docling poll status=%s elapsed=%ds", status, elapsed)
                    if status in ("success", "SUCCESS", "completed"):
                        break
                    if status in ("failure", "FAILURE", "failed"):
                        raise RuntimeError(f"Docling parsing failed: {status_data}")
                    time.sleep(DOCLING_POLL_INTERVAL)
                    elapsed += DOCLING_POLL_INTERVAL
                else:
                    raise TimeoutError(f"Docling timeout after {DOCLING_TIMEOUT}s")

                result_resp = client.get(
                    f"{settings.DOCLING_BASE_URL}/v1/result/{task_id}"
                )
                result_resp.raise_for_status()
                result_data = result_resp.json()

            # Extract markdown text from result
            # Docling returns {"document": {"md_content": "..."}}
            doc_obj = result_data.get("document", {})
            markdown_text = (
                doc_obj.get("md_content")
                or doc_obj.get("markdown")
                or result_data.get("markdown", "")
                or ""
            )
            if not markdown_text:
                # Fallback: concat chunks if present
                for chunk in doc_obj.get("chunks", []) or []:
                    markdown_text += chunk.get("text", "") + "\n\n"
            if not markdown_text:
                markdown_text = str(result_data)

            logger.info("Parsed %d chars of text", len(markdown_text))

            # Strip inline base64 images (không embed vào chunk)
            markdown_text = _strip_embedded_images(markdown_text)

        # ── Step 5: Auto-classify doc_type nếu chưa có ───────────────────
        if not doc.doc_type:
            doc.doc_type = _classify_doc_type(markdown_text, doc.filename)
            doc.save(update_fields=["doc_type"])
            logger.info("Auto-classified doc_type=%s for %s", doc.doc_type, doc.filename)

        # ── Step 7: Save parsed text to MinIO ─────────────────────────────
        parsed_path = f"{doc.id}/parsed.md"
        markdown_bytes = markdown_text.encode("utf-8")
        minio.put_object(
            bucket_name=settings.MINIO_BUCKET_PARSED,
            object_name=parsed_path,
            data=io.BytesIO(markdown_bytes),
            length=len(markdown_bytes),
            content_type="text/markdown",
        )
        doc.minio_path_parsed = parsed_path
        doc.save(update_fields=["minio_path_parsed"])

        # ── Step 8: Chunk ──────────────────────────────────────────────────
        chunks = _chunk_text(markdown_text)
        logger.info("Created %d chunks", len(chunks))

        if not chunks:
            raise ValueError("No chunks extracted from document")

        # ── Step 9: Embed + upsert to Qdrant ──────────────────────────────
        qdrant = QdrantClient(url=settings.QDRANT_URL)
        points = []
        for i, chunk in enumerate(chunks):
            vector = _embed_text(chunk)
            if i == 0:
                _ensure_collection(qdrant, len(vector))
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "text": chunk,
                        "source": doc.filename,
                        "doc_type": doc.doc_type,
                        "document_id": str(doc.id),
                        "chunk_index": i,
                    },
                )
            )

        qdrant.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
        logger.info("Upserted %d vectors to Qdrant", len(points))

        # ── Step 10: Mark done ─────────────────────────────────────────────
        job.status = IngestionJob.Status.DONE
        job.save(update_fields=["status", "updated_at"])
        logger.info("Ingestion complete job_id=%s", job_id)

    except Exception as exc:
        logger.error("Ingestion failed job_id=%s error=%s", job_id, str(exc), exc_info=True)
        job.status = IngestionJob.Status.FAILED
        job.error = str(exc)
        job.save(update_fields=["status", "error", "updated_at"])
        raise self.retry(exc=exc)
