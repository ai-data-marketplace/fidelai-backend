import logging
from django.db import transaction
from django.utils import timezone
from apps.processing.models import Chunk, ChunkStatusChoices
from apps.processing.models.ai import AIQualityCheck
from ai_models.scripts.model_loader import AmharicSafetyModel, TextQualityModel

logger = logging.getLogger(__name__)


class AIQualityCheckService:
    _qc_model_instance = None
    _safety_model_instance = None
    _qc_model_name = "amanfisseha/multihead-rasyosef-amharic"
    _safety_model_name = "uhhlt/amharic-hate-speech"
    _model_version = "1.0"  

    @classmethod
    def get_qc_model(cls):
        if cls._qc_model_instance is None:
            logger.info("Loading AI QC model: %s", cls._qc_model_name)
            cls._qc_model_instance = TextQualityModel(cls._qc_model_name)
            logger.info("AI QC model loaded: %s", cls._qc_model_name)
        return cls._qc_model_instance

    @classmethod
    def get_safety_model(cls):
        if cls._safety_model_instance is None:
            logger.info("Loading safety model: %s", cls._safety_model_name)
            cls._safety_model_instance = AmharicSafetyModel(cls._safety_model_name)
            logger.info("Safety model loaded: %s", cls._safety_model_name)
        return cls._safety_model_instance

    def process_pending_chunks(self, batch_size=100):
        qs = (
            Chunk.objects.filter(status=ChunkStatusChoices.PENDING)
            .exclude(text__isnull=True)
            .exclude(text__exact="")
            .select_related("extracted_document", "extracted_document__raw_document")
        )
        total_pending = qs.count()
        logger.info(
            "AI QC batch started: pending_chunks=%s batch_size=%s",
            total_pending,
            batch_size,
        )
        chunk_ids = list(qs.values_list("id", flat=True))
        processed = 0
        for chunk_id in chunk_ids:
            chunk = None
            try:
                chunk = (
                    Chunk.objects.select_related("extracted_document", "extracted_document__raw_document")
                    .get(id=chunk_id)
                )
                self._process_single_chunk(chunk)
                processed += 1
            except Exception as e:
                logger.error(f"AI QC failed for chunk {chunk_id}: {e}")
                if chunk is None:
                    chunk = Chunk.objects.filter(id=chunk_id).first()
                if chunk is not None:
                    chunk.metadata = chunk.metadata or {}
                    chunk.metadata["ai_qc_error"] = str(e)
                    chunk.save(update_fields=["metadata"])
        logger.info(
            "AI QC batch completed: processed=%s pending_at_start=%s",
            processed,
            total_pending,
        )
        return processed

    def _process_single_chunk(self, chunk):
        with transaction.atomic():
            if hasattr(chunk, "ai_quality_check"):
                return
            qc_output = self.run_qc_model_inference(chunk.text)
            if qc_output is None:
                raise RuntimeError("QC model inference failed or returned None")
            safety_output = self.run_safety_model_inference(chunk.text)
            if safety_output is None:
                raise RuntimeError("Safety model inference failed or returned None")

            lang = qc_output["language"]["label"]
            lang_conf = float(qc_output["language"]["confidence"])
            dom = qc_output["domain"]["label"]
            dom_conf = float(qc_output["domain"]["confidence"])
            read = qc_output["readability"]["label"]
            read_conf = float(qc_output["readability"]["confidence"])
            safety = safety_output["label"]
            safety_conf = float(safety_output["score"])
            quality_score = self.compute_quality_score(lang_conf, dom_conf, read_conf)
            status = self.determine_chunk_status(
                language_label=lang,
                lang_conf=lang_conf,
                domain_label=dom,
                dom_conf=dom_conf,
                readability_label=read,
                read_conf=read_conf,
                safety_label=safety,
                safety_conf=safety_conf,
                expected_domain=getattr(chunk.extracted_document.raw_document, "domain", None),
            )

            AIQualityCheck.objects.create(
                chunk=chunk,
                predicted_language=lang,
                language_confidence=lang_conf,
                predicted_domain=dom,
                domain_confidence=dom_conf,
                predicted_readability=read,
                readability_confidence=read_conf,
                predicted_safety=safety,
                safety_confidence=safety_conf,
                model_name=f"{self._qc_model_name}; {self._safety_model_name}",
                model_version=self._model_version,
                raw_qc_output=qc_output,
                raw_safety_output=safety_output,
                processed_at=timezone.now(),
            )
            chunk.quality_score = quality_score
            chunk.status = status
            chunk.save(update_fields=["quality_score", "status"])
            logger.info(
                "AI QC processed chunk=%s status=%s quality_score=%.4f language=%s:%.4f domain=%s:%.4f readability=%s:%.4f safety=%s:%.4f",
                chunk.id,
                status,
                quality_score,
                lang,
                lang_conf,
                dom,
                dom_conf,
                read,
                read_conf,
                safety,
                safety_conf,
            )

    def run_qc_model_inference(self, text):
        try:
            model = self.get_qc_model()
            return model.predict(text)
        except Exception as e:
            logger.error(f"QC model inference error: {e}")
            return None

    def run_safety_model_inference(self, text):
        try:
            model = self.get_safety_model()
            return model.predict(text)
        except Exception as e:
            logger.error(f"Safety model inference error: {e}")
            return None

    @staticmethod
    def compute_quality_score(language_conf, domain_conf, readability_conf):
        score = language_conf * 0.4 + domain_conf * 0.3 + readability_conf * 0.3
        return max(0.0, min(1.0, score))

    @staticmethod
    def determine_chunk_status(
        *,
        language_label,
        lang_conf,
        domain_label,
        dom_conf,
        readability_label,
        read_conf,
        safety_label,
        safety_conf,
        expected_domain=None,
    ):
        if safety_label in {"hate", "offensive"}:
            return ChunkStatusChoices.REJECTED

        qc_has_rejected_labels = (
            language_label == "Other/Mixed"
            and readability_label == "Broken/OCR"
            and not AIQualityCheckService.domain_matches_expected(domain_label, expected_domain)
        )
        if qc_has_rejected_labels:
            return ChunkStatusChoices.REJECTED

        qc_has_approved_labels = (
            language_label == "Amharic"
            and readability_label == "Clear"
            and AIQualityCheckService.domain_matches_expected(domain_label, expected_domain)
        )
        qc_is_high_confidence = lang_conf >= 0.90 and dom_conf >= 0.90 and read_conf >= 0.90
        safety_is_clear = safety_label == "normal" and safety_conf >= 0.75
        if qc_has_approved_labels and qc_is_high_confidence and safety_is_clear:
            return ChunkStatusChoices.APPROVED

        return ChunkStatusChoices.AI_LOW_CONFIDENCE

    @staticmethod
    def domain_matches_expected(predicted_domain, expected_domain):
        if not expected_domain:
            return True

        predicted = str(predicted_domain).strip().lower().replace("_", " ")
        expected = str(expected_domain).strip().lower().replace("_", " ")

        if predicted == expected:
            return True

        return {predicted, expected} == {"general", "other"}
