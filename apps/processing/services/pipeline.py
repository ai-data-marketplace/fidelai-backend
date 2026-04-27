from dataclasses import asdict
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.processing.models import ExtractedDocument

from .assembler import DocumentStructureAssemblerService
from .document_loader import DocumentIngestionService
from .docx_extractor import DOCXExtractionService
from .language_detection import LanguageDetectionService
from .layout_analysis import LayoutAnalysisService
from .ocr import OCRService
from .pdf_text_extractor import PDFExtractionService
from .text_cleaning import TextCleaningService


class DocumentProcessingPipelineService:
    """Celery-facing orchestration service for document preprocessing."""

    def __init__(self):
        self.ingestion_service = DocumentIngestionService()
        self.ocr_service = OCRService()
        self.pdf_service = PDFExtractionService()
        self.docx_service = DOCXExtractionService()
        self.layout_service = LayoutAnalysisService()
        self.cleaning_service = TextCleaningService()
        self.language_service = LanguageDetectionService()
        self.assembler_service = DocumentStructureAssemblerService()

    def _read_file_bytes(self, raw_document):
        file_record = self.ingestion_service.get_latest_file_record(raw_document)
        if not file_record:
            raise ValidationError(f"RawDocument {raw_document.pk} does not have an uploaded file attached.")

        with file_record.file.open("rb") as file_handle:
            return file_handle.read(), file_record

    def run(self, raw_document):
        file_bytes, file_record = self._read_file_bytes(raw_document)
        ingestion_result = self.ingestion_service.load(raw_document)

        if ingestion_result.extension == "docx":
            extracted = self.docx_service.extract(file_bytes)
            pages = [{"page": 1, "blocks": extracted.blocks, "text": extracted.text, "confidence": extracted.confidence}]
            ordered_text = extracted.text
        elif ingestion_result.extension == "pdf":
            pdf_result = self.pdf_service.extract(file_bytes)
            if not pdf_result or not any(page.text.strip() for page in pdf_result):
                ocr_result = self.ocr_service.extract_page_text(file_bytes, page_number=1)
                pages = [{"page": ocr_result.page_number, "blocks": ocr_result.blocks, "text": ocr_result.text, "confidence": ocr_result.confidence}]
                ordered_text = ocr_result.text
            else:
                pages = [{"page": page.page_number, "blocks": page.blocks, "text": page.text, "confidence": page.confidence} for page in pdf_result]
                ordered_text = "\n".join(page["text"] for page in pages)
        else:
            ocr_result = self.ocr_service.extract_page_text(file_bytes, page_number=1)
            pages = [{"page": ocr_result.page_number, "blocks": ocr_result.blocks, "text": ocr_result.text, "confidence": ocr_result.confidence}]
            ordered_text = ocr_result.text

        layout_result = self.layout_service.build_structure(pages)
        cleaned_text = self.cleaning_service.merge_fragments(
            self.cleaning_service.clean_ocr_noise(
                self.cleaning_service.normalize_amharic_unicode(
                    layout_result.ordered_text if getattr(layout_result, "ordered_text", None) else ordered_text,
                )
            )
        )
        language_result = self.language_service.detect(cleaned_text)

        payload = self.assembler_service.assemble(
            full_text=cleaned_text,
            structure=getattr(layout_result, "structured_blocks", pages),
            layout_metadata={
                **getattr(layout_result, "layout_metadata", {}),
                **ingestion_result.metadata,
                "file_hash": ingestion_result.file_hash,
                "file_name": ingestion_result.file_name,
                "source_type": ingestion_result.source_type,
                "uploaded_file_name": getattr(file_record.file, "name", Path(file_record.file.path).name),
            },
            language_detected=language_result.language_detected,
            confidence_score=language_result.confidence_score,
            processed_at=timezone.now(),
        )

        extracted_document, _ = ExtractedDocument.objects.update_or_create(
            raw_document=raw_document,
            defaults=asdict(payload),
        )
        return extracted_document