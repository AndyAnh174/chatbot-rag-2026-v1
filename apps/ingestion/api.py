import uuid

from django.shortcuts import get_object_or_404
from ninja import Router, File
from ninja.files import UploadedFile

from .schemas import DeleteResponse, DocumentListResponse, DocumentSchema, IngestionResponse, JobStatusResponse

router = Router()


@router.post("/", response=IngestionResponse)
def upload_document(request, file: UploadedFile = File(...), doc_type: str = ""):
    from .services import enqueue_ingestion
    job_id, document_id = enqueue_ingestion(file, doc_type)
    return IngestionResponse(job_id=job_id, document_id=document_id, status="queued")


@router.get("/status/{job_id}/", response=JobStatusResponse)
def job_status(request, job_id: uuid.UUID):
    from .models import IngestionJob
    job = get_object_or_404(IngestionJob, id=job_id)
    return JobStatusResponse(job_id=job.id, status=job.status, error=job.error)


@router.get("/documents/", response=DocumentListResponse)
def list_documents(request):
    from .models import Document
    docs = Document.objects.prefetch_related("jobs").order_by("-created_at")
    items = []
    for doc in docs:
        latest_job = doc.jobs.order_by("-created_at").first()
        items.append(DocumentSchema(
            id=doc.id,
            filename=doc.filename,
            doc_type=doc.doc_type,
            content_type=doc.content_type,
            created_at=doc.created_at.strftime("%Y-%m-%d %H:%M"),
            job_status=latest_job.status if latest_job else None,
            job_error=latest_job.error if latest_job else None,
        ))
    return DocumentListResponse(documents=items, total=len(items))


@router.delete("/documents/{document_id}/", response=DeleteResponse)
def delete_document(request, document_id: uuid.UUID):
    from .models import Document
    from .services import delete_document as svc_delete
    doc = get_object_or_404(Document, id=document_id)
    result = svc_delete(doc)
    return DeleteResponse(document_id=document_id, **result)
