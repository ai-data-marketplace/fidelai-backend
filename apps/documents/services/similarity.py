import re
import logging
from apps.documents.models import RawDocument, ReviewStatusChoices
from apps.processing.models import ExtractedDocument

logger = logging.getLogger(__name__)

class SimilarityService:
    """Dedicated service for content-based similarity checks using containment logic."""
    
    THRESHOLD = 0.70

    def generate_signature(self, text: str) -> list[str]:
        """
        Generate a representation of the text for similarity checking.
        For containment logic, we return a list of unique alphanumeric tokens.
        """
        if not text:
            return []
        # Return unique tokens as a list so it can be serialized to JSON
        return list(set(re.findall(r'\w+', text.lower())))

    def check_duplicate(self, raw_document: RawDocument, current_text: str) -> tuple[bool, dict]:
        """
        Compare the current text against existing approved/pending documents.
        Returns (True, details) if the new document's text is largely contained within an existing one (>= 70%).
        """
        if not current_text:
            return False, {}
            
        # Extract alphanumeric tokens using our new signature method
        current_tokens_list = self.generate_signature(current_text)
        current_tokens = set(current_tokens_list)
        if not current_tokens:
            return False, {}
            
        current_len = len(current_tokens)
        
        # Determine the name of the incoming document for logging
        new_file = raw_document.files.first()
        new_file_name = new_file.file_name if new_file else f"RawDoc-{raw_document.id}"
        
        existing_docs = ExtractedDocument.objects.exclude(raw_document_id=raw_document.id).filter(
            raw_document__review_status__in=[ReviewStatusChoices.APPROVED, ReviewStatusChoices.PENDING_REVIEW]
        ).select_related('raw_document').prefetch_related('raw_document__files')
        
        for doc in existing_docs:
            if not doc.full_text:
                continue
                
            existing_file = doc.raw_document.files.first()
            existing_file_name = existing_file.file_name if existing_file else f"RawDoc-{doc.raw_document_id}"
                
            # Log the comparison
            logger.info("Comparing [%s] against [%s]", new_file_name, existing_file_name)
            
            # Use cached signature if available, otherwise tokenize full text
            if doc.similarity_signature:
                existing_tokens = set(doc.similarity_signature)
            else:
                existing_tokens = set(self.generate_signature(doc.full_text))
                
            if not existing_tokens:
                continue
                
            # Compute containment
            intersection = current_tokens.intersection(existing_tokens)
            score = len(intersection) / current_len
            
            logger.info("Similarity Score: %.2f%%", score * 100)
            
            if score >= self.THRESHOLD:
                warning_msg = f"WARNING: Conflicting files detected! [{new_file_name}] is contained in [{existing_file_name}] (Score: {score * 100:.2f}%)"
                logger.warning(warning_msg)
                return True, {
                    "score": score * 100,
                    "new_file": new_file_name,
                    "existing_file": existing_file_name
                }
                
        return False, {}
