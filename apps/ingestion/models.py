import uuid
from django.db import models


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=512)
    content_type = models.CharField(max_length=128)
    minio_path_raw = models.CharField(max_length=1024)
    minio_path_parsed = models.CharField(max_length=1024, blank=True)
    doc_type = models.CharField(max_length=64, blank=True)  # e.g. "sotay", "ctdt", "qd"
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename


class IngestionJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.document.filename} — {self.status}"
