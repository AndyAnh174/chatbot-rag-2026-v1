import io
import uuid
import logging

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from minio import Minio
from minio.error import S3Error
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from .models import Document, IngestionJob

logger = logging.getLogger(__name__)


def _get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


def enqueue_ingestion(file: UploadedFile, doc_type: str = "") -> tuple[uuid.UUID, uuid.UUID]:
    """
    1. Upload raw file to MinIO documents-raw
    2. Create Document + IngestionJob DB records
    3. Dispatch Celery task
    Returns (job_id, document_id)
    """
    from .tasks import process_document

    client = _get_minio_client()
    file_id = uuid.uuid4()
    minio_path = f"{file_id}/{file.name}"

    # Read file content
    file_bytes = file.read()
    file_size = len(file_bytes)

    # Upload to MinIO
    client.put_object(
        bucket_name=settings.MINIO_BUCKET_RAW,
        object_name=minio_path,
        data=io.BytesIO(file_bytes),
        length=file_size,
        content_type=file.content_type or "application/octet-stream",
    )
    logger.info("Uploaded %s to MinIO path %s", file.name, minio_path)

    # Create DB records
    doc = Document.objects.create(
        filename=file.name,
        content_type=file.content_type or "application/octet-stream",
        minio_path_raw=minio_path,
        doc_type=doc_type,
    )
    job = IngestionJob.objects.create(
        document=doc,
        status=IngestionJob.Status.QUEUED,
    )

    # Dispatch Celery task
    process_document.delay(str(job.id), str(doc.id))
    logger.info("Dispatched ingestion task job_id=%s document_id=%s", job.id, doc.id)

    return job.id, doc.id


def delete_document(doc: Document) -> dict:
    """
    Xóa hoàn toàn một document:
    1. Xóa vectors trong Qdrant (filter by document_id)
    2. Xóa raw file trong MinIO
    3. Xóa parsed file trong MinIO (nếu có)
    4. Xóa Document (cascade xóa IngestionJob)
    """
    doc_id = str(doc.id)
    minio = _get_minio_client()
    qdrant = QdrantClient(url=settings.QDRANT_URL)

    # 1. Xóa vectors Qdrant
    try:
        qdrant.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]
            ),
        )
        logger.info("Deleted Qdrant vectors for document_id=%s", doc_id)
    except Exception as exc:
        logger.warning("Could not delete Qdrant vectors for %s: %s", doc_id, exc)

    # 2. Xóa raw file MinIO
    try:
        minio.remove_object(settings.MINIO_BUCKET_RAW, doc.minio_path_raw)
        logger.info("Deleted MinIO raw: %s", doc.minio_path_raw)
    except S3Error as exc:
        logger.warning("Could not delete MinIO raw %s: %s", doc.minio_path_raw, exc)

    # 3. Xóa parsed file MinIO
    if doc.minio_path_parsed:
        try:
            minio.remove_object(settings.MINIO_BUCKET_PARSED, doc.minio_path_parsed)
            logger.info("Deleted MinIO parsed: %s", doc.minio_path_parsed)
        except S3Error as exc:
            logger.warning("Could not delete MinIO parsed %s: %s", doc.minio_path_parsed, exc)

    # 4. Xóa DB (cascade xóa IngestionJob)
    doc.delete()
    logger.info("Deleted Document id=%s filename=%s", doc_id, doc.filename)

    return {"deleted": True, "message": f"Đã xóa '{doc.filename}' và toàn bộ vectors liên quan."}
