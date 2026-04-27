from dataclasses import dataclass
from hashlib import sha256
from mimetypes import guess_type
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError

try:
    import magic  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    magic = None


@dataclass(frozen=True)
class IngestionResult:
    file_name: str
    file_path: str
    mime_type: str
    file_hash: str
    source_type: str
    extension: str
    metadata: dict[str, Any]


class DocumentIngestionService:
    """Detects file type, validates integrity, and routes the document to the proper extractor."""

    SUPPORTED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}

    def get_latest_file_record(self, raw_document):
        return raw_document.files.order_by("-uploaded_at", "-created_at", "-pk").first()

    def detect_file_type(self, file_path: str) -> str:
        extension = Path(file_path).suffix.lower().lstrip(".")
        if not extension:
            raise ValidationError("Uploaded file must have an extension.")
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValidationError(f"Unsupported file type: {extension}")
        return extension

    def detect_mime_type(self, file_path: str) -> str:
        if magic is not None:
            try:
                return magic.from_file(file_path, mime=True)
            except Exception:
                pass

        guessed_mime_type, _ = guess_type(file_path)
        return guessed_mime_type or "application/octet-stream"

    def validate_file_integrity(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ValidationError("Uploaded file is missing or invalid.")

        digest = sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def route(self, file_path: str, mime_type: str | None = None) -> IngestionResult:
        extension = self.detect_file_type(file_path)
        file_hash = self.validate_file_integrity(file_path)
        detected_mime_type = mime_type or self.detect_mime_type(file_path)
        source_type = "pdf" if extension == "pdf" else "docx" if extension == "docx" else "image"
        metadata = {
            "mime_type": detected_mime_type,
            "is_pdf": extension == "pdf",
            "is_docx": extension == "docx",
            "requires_ocr": extension in {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"},
        }
        return IngestionResult(
            file_name=Path(file_path).name,
            file_path=file_path,
            mime_type=detected_mime_type,
            file_hash=file_hash,
            source_type=source_type,
            extension=extension,
            metadata=metadata,
        )

    def load(self, raw_document) -> IngestionResult:
        file_record = self.get_latest_file_record(raw_document)
        if not file_record:
            raise ValidationError(f"RawDocument {raw_document.pk} does not have an uploaded file attached.")

        mime_type = getattr(file_record.file, "content_type", None)
        return self.route(file_record.file.path, mime_type)


DocumentLoaderService = DocumentIngestionService