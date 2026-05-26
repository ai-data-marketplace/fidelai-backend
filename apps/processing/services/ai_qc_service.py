import logging
from django.db import transaction
from django.utils import timezone
from apps.processing.models import Chunk, ChunkStatusChoices
from apps.processing.models.ai import AIQualityCheck
from ai_models.scripts.model_loader import TextQualityModel

logger = logging.getLogger(__name__)


class AIQualityCheckService:
    _model_instance = None
    _model_name = "amanfisseha/multihead-rasyosef-amharic"
    _model_version = "1.0"  

    @classmethod
    def get_model(cls):
        if cls._model_instance is None:
            cls._model_instance = TextQualityModel(cls._model_name)
        return cls._model_instance

    def process_pending_chunks(self, batch_size=100):
        qs = (
            Chunk.objects.filter(status=ChunkStatusChoices.PENDING)
            .exclude(text__isnull=True)
            .exclude(text__exact="")
            .select_related("extracted_document")
        )
        processed = 0
        for chunk in qs.iterator(chunk_size=batch_size):
            try:
                self._process_single_chunk(chunk)
                processed += 1
            except Exception as e:
                logger.error(f"AI QC failed for chunk {chunk.id}: {e}")
                chunk.metadata = chunk.metadata or {}
                chunk.metadata["ai_qc_error"] = str(e)
                chunk.save(update_fields=["metadata"])
        return processed

    def _process_single_chunk(self, chunk):
        from django.db import IntegrityError
        with transaction.atomic():
            if hasattr(chunk, "ai_quality_check"):
                return
            preds = self.run_model_inference(chunk.text)
            if preds is None:
                raise RuntimeError("Model inference failed or returned None")
            lang = preds["language"]["label"]
            lang_conf = float(preds["language"]["confidence"])
            dom = preds["domain"]["label"]
            dom_conf = float(preds["domain"]["confidence"])
            read = preds["readability"]["label"]
            read_conf = float(preds["readability"]["confidence"])
            quality_score = self.compute_quality_score(lang_conf, dom_conf, read_conf)
            manual_review = self.requires_manual_review(chunk, lang_conf, dom_conf, read_conf)
            aiqc = AIQualityCheck.objects.create(
                chunk=chunk,
                predicted_language=lang,
                language_confidence=lang_conf,
                predicted_domain=dom,
                domain_confidence=dom_conf,
                predicted_readability=read,
                readability_confidence=read_conf,
                overall_confidence_score=quality_score,
                requires_manual_review=manual_review,
                model_name=self._model_name,
                model_version=self._model_version,
                raw_predictions=preds,
                processed_at=timezone.now(),
            )
            chunk.quality_score = quality_score
            if read_conf < 0.75:
                chunk.status = ChunkStatusChoices.REJECTED
            else:
                chunk.status = ChunkStatusChoices.AI_PROCESSED
            chunk.save(update_fields=["quality_score", "status"])

    def run_model_inference(self, text):
        try:
            model = self.get_model()
            return model.predict(text)
        except Exception as e:
            logger.error(f"Model inference error: {e}")
            return None

    @staticmethod
    def compute_quality_score(language_conf, domain_conf, readability_conf):
        score = language_conf * 0.4 + domain_conf * 0.3 + readability_conf * 0.3
        return max(0.0, min(1.0, score))

    @staticmethod
    def requires_manual_review(chunk, lang_conf, dom_conf, read_conf):
        if lang_conf < 0.70 or read_conf < 0.60 or dom_conf < 0.60:
            return True
        if chunk.token_count is not None and chunk.token_count < 5:
            return True
        if chunk.text is not None and len(chunk.text.strip()) < 20:
            return True
        import re
        if chunk.text and re.search(r"[\u202e\u202d\u200b\u200e\u200f\ufffd]", chunk.text):
            return True
        if chunk.text and sum(1 for c in chunk.text if not c.isprintable()) > 0:
            return True
        return False
