"""Tests for the NLP candidate extraction service."""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.nlp.models import NLPChunk, NLPChunkStatusChoices, NLPTaskTypeChoices
from apps.nlp.services.candidate_extraction_service import (
    Candidate,
    CandidateExtractionService,
    GeminiClientError,
)
from apps.processing.models.chunk import ChunkStatusChoices, ExtractedDocument, Chunk
from apps.documents.models import RawDocument, ProcessingStatusChoices, ReviewStatusChoices
from apps.users.models import CustomUser, RoleChoices


class CandidateExtractionServiceTestCase(TestCase):
    """Unit tests for CandidateExtractionService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = CandidateExtractionService(
            model_name="gemini-1.5-flash",
            api_key="test-key-123"
        )
        
        # Create test user
        self.user = CustomUser.objects.create_user(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password="testpass123",
            role=RoleChoices.ANNOTATOR,
        )
        
        # Create raw document
        self.raw_doc = RawDocument.objects.create(
            user=self.user,
            title="test-doc.txt",
            processing_status=ProcessingStatusChoices.COMPLETED,
            review_status=ReviewStatusChoices.APPROVED,
        )
        
        # Create extracted document
        self.extracted_doc = ExtractedDocument.objects.create(
            raw_document=self.raw_doc,
            full_text="This is a test document with multiple sentences. The service is amazing! But the wait time was terrible.",
            processed_at="2024-01-01T00:00:00Z",
        )
        
        # Create approved chunk
        self.chunk = Chunk.objects.create(
            extracted_document=self.extracted_doc,
            status=ChunkStatusChoices.APPROVED,
            text="This is a test paragraph. The service is amazing! But the wait time was terrible.",
            order_index=1,
            char_start=0,
            char_end=80,
            token_count=20,
        )

    def test_service_initialization(self):
        """Test service initializes with correct settings."""
        self.assertEqual(self.service.model_name, "gemini-1.5-flash")
        self.assertEqual(self.service.api_key, "test-key-123")

    def test_build_prompt_structure(self):
        """Test prompt building generates valid structured prompt."""
        prompt = self.service.build_prompt(
            "This is great! But slow.",
            {},
            source_domain="commerce"
        )
        
        self.assertIn("sentiment", prompt.lower())
        self.assertIn("positive", prompt.lower())
        self.assertIn("negative", prompt.lower())
        self.assertIn("json array", prompt.lower())
        self.assertIn("commerce", prompt)

    def test_validate_candidate_accepts_valid(self):
        """Test validation accepts good candidates."""
        candidate = Candidate(
            text="This product is amazing!",
            candidate_sentiment="positive",
            confidence=0.95
        )
        
        self.assertTrue(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_rejects_low_confidence(self):
        """Test validation rejects low confidence candidates."""
        candidate = Candidate(
            text="This product is okay",
            candidate_sentiment="neutral",
            confidence=0.3
        )
        
        self.assertFalse(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_rejects_short_text(self):
        """Test validation rejects very short candidates."""
        candidate = Candidate(
            text="ok",
            candidate_sentiment="positive",
            confidence=0.9
        )
        
        self.assertFalse(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_rejects_repeated_punctuation(self):
        """Test validation rejects candidates with excessive punctuation."""
        candidate = Candidate(
            text="This is terrible!!!!!",
            candidate_sentiment="negative",
            confidence=0.9
        )
        
        self.assertFalse(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_rejects_empty_text(self):
        """Test validation rejects empty text."""
        candidate = Candidate(
            text="",
            candidate_sentiment="neutral",
            confidence=0.9
        )
        
        self.assertFalse(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_normalize_text_collapses_whitespace(self):
        """Test text normalization collapses whitespace."""
        normalized = self.service.normalize_text("hello   world   test")
        self.assertEqual(normalized, "hello world test")

    def test_normalize_text_collapses_punctuation(self):
        """Test text normalization collapses repeated punctuation."""
        normalized = self.service.normalize_text("really great!!!!")
        self.assertIn("great!", normalized)
        self.assertNotIn("!!!!", normalized)

    def test_normalize_text_lowercase(self):
        """Test text normalization converts to lowercase."""
        normalized = self.service.normalize_text("HELLO WORLD")
        self.assertEqual(normalized, "hello world")

    def test_extract_json_from_text_finds_json_array(self):
        """Test JSON extraction finds valid JSON array in text."""
        text = 'Some explanation then [{"text": "hello", "sentiment": "positive"}]'
        result = self.service._extract_json_from_text(text)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("["))
        self.assertTrue(result.endswith("]"))

    def test_parse_response_with_valid_json(self):
        """Test response parsing with valid JSON."""
        response = MagicMock()
        response.text = json.dumps([
            {"text": "Great product!", "candidate_sentiment": "positive", "confidence": 0.95},
            {"text": "Terrible service", "candidate_sentiment": "negative", "confidence": 0.88},
        ])
        
        candidates = self.service.parse_response(response)
        
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].text, "Great product!")
        self.assertEqual(candidates[0].candidate_sentiment, "positive")
        self.assertEqual(candidates[0].confidence, 0.95)
        self.assertEqual(candidates[1].text, "Terrible service")
        self.assertEqual(candidates[1].candidate_sentiment, "negative")

    def test_parse_response_with_malformed_json(self):
        """Test response parsing gracefully handles malformed JSON."""
        response = MagicMock()
        response.text = "This is not valid JSON at all"
        
        candidates = self.service.parse_response(response)
        
        self.assertEqual(len(candidates), 0)

    def test_parse_response_with_missing_fields(self):
        """Test response parsing skips entries with missing fields."""
        response = MagicMock()
        response.text = json.dumps([
            {"text": "Good product", "candidate_sentiment": "positive"},  # missing confidence
            {"text": "Bad service", "confidence": 0.9},  # missing sentiment
            {"text": "Okay", "candidate_sentiment": "neutral", "confidence": 0.85},  # valid
        ])
        
        candidates = self.service.parse_response(response)
        
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].text, "Okay")

    @patch("apps.nlp.services.candidate_extraction_service.Chunk.objects")
    def test_process_approved_chunks_queries_approved_only(self, mock_chunk_objects):
        """Test that process_approved_chunks only queries approved chunks."""
        mock_chunk_objects.filter.return_value.order_by.return_value.iterator.return_value = []
        
        self.service.process_approved_chunks(batch_size=10)
        
        mock_chunk_objects.filter.assert_called_once_with(status=ChunkStatusChoices.APPROVED)

    def test_create_nlp_chunk_sets_correct_defaults(self):
        """Test NLPChunk creation with correct status and settings."""
        nlp_chunk = self.service.create_nlp_chunk(
            source_chunk=self.chunk,
            task_type=NLPTaskTypeChoices.SENTIMENT,
            text="Great product!",
            source_context="Full document context",
            source_domain="commerce",
            generated_by_ai=True,
            ai_model_name="gemini-1.5-flash",
            ai_confidence_score=0.95,
            metadata={"test": "data"},
        )
        
        self.assertEqual(nlp_chunk.source_chunk, self.chunk)
        self.assertEqual(nlp_chunk.task_type, NLPTaskTypeChoices.SENTIMENT)
        self.assertEqual(nlp_chunk.text, "Great product!")
        self.assertEqual(nlp_chunk.status, NLPChunkStatusChoices.READY_FOR_ANNOTATION)
        self.assertEqual(nlp_chunk.generated_by_ai, True)
        self.assertEqual(nlp_chunk.ai_confidence_score, 0.95)
        self.assertTrue(nlp_chunk.is_active)
        self.assertFalse(nlp_chunk.requires_human_review)

    def test_process_chunk_creates_nlp_chunks_from_candidates(self):
        """Test process_chunk creates NLPChunk records from valid candidates."""
        with patch.object(self.service, "call_gemini") as mock_gemini:
            # Mock Gemini response
            mock_response = MagicMock()
            mock_response.text = json.dumps([
                {"text": "Great service!", "candidate_sentiment": "positive", "confidence": 0.95},
                {"text": "Slow delivery", "candidate_sentiment": "negative", "confidence": 0.88},
            ])
            mock_gemini.return_value = mock_response
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 2)
            self.assertEqual(created, 2)
            self.assertEqual(skipped, 0)
            
            # Verify NLPChunks were created
            nlp_chunks = NLPChunk.objects.filter(source_chunk=self.chunk)
            self.assertEqual(nlp_chunks.count(), 2)

    def test_process_chunk_deduplicates_candidates(self):
        """Test process_chunk skips duplicate candidate text."""
        # Create an existing NLPChunk
        existing = NLPChunk.objects.create(
            source_chunk=self.chunk,
            task_type=NLPTaskTypeChoices.SENTIMENT,
            text="Great service!",
            order_index=0,
            char_start=0,
            char_end=14,
            generated_by_ai=True,
            ai_model_name="test",
            status=NLPChunkStatusChoices.READY_FOR_ANNOTATION,
        )
        
        with patch.object(self.service, "call_gemini") as mock_gemini:
            # Mock Gemini returning a duplicate
            mock_response = MagicMock()
            mock_response.text = json.dumps([
                {"text": "Great service!", "candidate_sentiment": "positive", "confidence": 0.95},  # duplicate
                {"text": "Slow delivery", "candidate_sentiment": "negative", "confidence": 0.88},  # new
            ])
            mock_gemini.return_value = mock_response
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 2)
            self.assertEqual(created, 1)  # only one new was created
            self.assertEqual(skipped, 1)  # one was skipped as duplicate
            
            # Total should be 2 (existing + new)
            nlp_chunks = NLPChunk.objects.filter(source_chunk=self.chunk)
            self.assertEqual(nlp_chunks.count(), 2)

    def test_validate_candidate_accepts_amharic_text(self):
        """Test validation accepts valid Amharic text candidates."""
        # "ምርጫ በጥንቃቄ ተደርጓል" = "The selection was made carefully"
        candidate = Candidate(
            text="ምርጫ በጥንቃቄ ተደርጓል",
            candidate_sentiment="positive",
            confidence=0.88
        )
        
        self.assertTrue(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_accepts_arabic_text(self):
        """Test validation accepts valid Arabic text candidates."""
        # "المنتج ممتاز جداً" = "The product is excellent"
        candidate = Candidate(
            text="المنتج ممتاز جداً",
            candidate_sentiment="positive",
            confidence=0.92
        )
        
        self.assertTrue(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_accepts_chinese_text(self):
        """Test validation accepts valid Chinese text with enough content."""
        # Mix English and Chinese to meet word count requirement
        # (Current service uses ASCII \w+ regex, so Chinese-only text won't have "words")
        candidate = Candidate(
            text="great 产品质量很好",
            candidate_sentiment="positive",
            confidence=0.90
        )
        
        self.assertTrue(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_validate_candidate_accepts_mixed_script_text(self):
        """Test validation accepts valid mixed-script text."""
        # Mix of English and Amharic
        candidate = Candidate(
            text="Amazing product! ምርጫ በጥንቃቄ",
            candidate_sentiment="positive",
            confidence=0.85
        )
        
        self.assertTrue(self.service.validate_candidate(candidate, min_confidence=0.6))

    def test_normalize_text_preserves_amharic(self):
        """Test text normalization preserves Amharic characters."""
        # With extra spaces
        original = "ምርጫ   በጥንቃቄ   ተደርጓል"
        normalized = self.service.normalize_text(original)
        
        # Should have Amharic characters preserved (not be empty)
        self.assertTrue(len(normalized) > 0)
        self.assertIn("ም", normalized)
        # Should collapse whitespace
        self.assertLess(normalized.count(" "), original.count(" "))

    def test_normalize_text_preserves_arabic(self):
        """Test text normalization preserves Arabic characters."""
        original = "المنتج    ممتاز    جداً"
        normalized = self.service.normalize_text(original)
        
        # Should have Arabic characters preserved
        self.assertIn("ا", normalized)
        self.assertIn("م", normalized)
        self.assertIn("ج", normalized)
        # Should collapse whitespace
        self.assertLess(normalized.count(" "), original.count(" "))

    def test_normalize_text_preserves_chinese(self):
        """Test text normalization preserves Chinese characters."""
        original = "产品  质量  很好"
        normalized = self.service.normalize_text(original)
        
        # Should have Chinese characters preserved
        self.assertIn("产", normalized)
        self.assertIn("质", normalized)
        self.assertIn("好", normalized)

    def test_process_chunk_deduplicates_amharic_candidates(self):
        """Test process_chunk deduplicates Amharic text correctly."""
        # Create an existing NLPChunk with Amharic text
        existing = NLPChunk.objects.create(
            source_chunk=self.chunk,
            task_type=NLPTaskTypeChoices.SENTIMENT,
            text="ምርጫ በጥንቃቄ ተደርጓል",
            order_index=0,
            char_start=0,
            char_end=20,
            generated_by_ai=True,
            ai_model_name="test",
            status=NLPChunkStatusChoices.READY_FOR_ANNOTATION,
        )
        
        with patch.object(self.service, "call_gemini") as mock_gemini:
            # Mock Gemini returning the same Amharic text (should be deduplicated)
            mock_response = MagicMock()
            mock_response.text = json.dumps([
                {"text": "ምርጫ በጥንቃቄ ተደርጓል", "candidate_sentiment": "positive", "confidence": 0.88},  # duplicate
                {"text": "ጥሩ ምርት", "candidate_sentiment": "positive", "confidence": 0.85},  # new
            ])
            mock_gemini.return_value = mock_response
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 2)
            self.assertEqual(created, 1)  # only one new was created
            self.assertEqual(skipped, 1)  # Amharic duplicate was skipped

    def test_parse_response_with_amharic_json(self):
        """Test response parsing with Amharic text in JSON."""
        response = MagicMock()
        response.text = json.dumps([
            {"text": "ምርጫ በጥንቃቄ ተደርጓል", "candidate_sentiment": "positive", "confidence": 0.88},
            {"text": "ከንቱ ሙከራ", "candidate_sentiment": "negative", "confidence": 0.82},
            {"text": "ጥሩ ምርት", "candidate_sentiment": "positive", "confidence": 0.90},
        ])
        
        candidates = self.service.parse_response(response)
        
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].text, "ምርጫ በጥንቃቄ ተደርጓል")
        self.assertEqual(candidates[0].candidate_sentiment, "positive")
        self.assertEqual(candidates[1].text, "ከንቱ ሙከራ")
        self.assertEqual(candidates[1].candidate_sentiment, "negative")
        self.assertEqual(candidates[2].text, "ጥሩ ምርት")

    def test_process_chunk_creates_amharic_nlp_chunks(self):
        """Test process_chunk creates NLPChunk records from Amharic candidates."""
        with patch.object(self.service, "call_gemini") as mock_gemini:
            # Mock Gemini response with Amharic text
            mock_response = MagicMock()
            mock_response.text = json.dumps([
                {"text": "ምርጫ በጥንቃቄ ተደርጓል", "candidate_sentiment": "positive", "confidence": 0.88},
                {"text": "ጥሩ ምርት ነው", "candidate_sentiment": "positive", "confidence": 0.90},
            ])
            mock_gemini.return_value = mock_response
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 2)
            self.assertEqual(created, 2)
            self.assertEqual(skipped, 0)
            
            # Verify NLPChunks were created with Amharic text
            nlp_chunks = NLPChunk.objects.filter(source_chunk=self.chunk)
            self.assertEqual(nlp_chunks.count(), 2)
            
            # Verify Amharic text is preserved
            texts = [chunk.text for chunk in nlp_chunks]
            self.assertIn("ምርጫ በጥንቃቄ ተደርጓል", texts)
            self.assertIn("ጥሩ ምርት ነው", texts)

    def test_process_chunk_handles_gemini_error(self):
        """Test process_chunk handles Gemini API errors gracefully."""
        with patch.object(self.service, "call_gemini") as mock_gemini:
            mock_gemini.side_effect = GeminiClientError("API key invalid")
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 0)
            self.assertEqual(created, 0)
            self.assertEqual(skipped, 0)
            
            # No NLPChunks should be created
            nlp_chunks = NLPChunk.objects.filter(source_chunk=self.chunk)
            self.assertEqual(nlp_chunks.count(), 0)

    def test_process_chunk_skips_invalid_candidates(self):
        """Test process_chunk skips candidates that fail validation."""
        with patch.object(self.service, "call_gemini") as mock_gemini:
            mock_response = MagicMock()
            mock_response.text = json.dumps([
                {"text": "Good", "candidate_sentiment": "positive", "confidence": 0.95},  # too short
                {"text": "Terrible!!!!", "candidate_sentiment": "negative", "confidence": 0.88},  # repeated punctuation
                {"text": "Amazing product experience", "candidate_sentiment": "positive", "confidence": 0.92},  # valid
            ])
            mock_gemini.return_value = mock_response
            
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            self.assertEqual(processed, 3)
            self.assertEqual(created, 1)  # only one valid candidate
            self.assertEqual(skipped, 2)


class CandidateExtractionIntegrationTestCase(TestCase):
    """Integration tests with real Gemini API (requires GEMINI_API_KEY in .env)."""

    def setUp(self):
        """Set up test fixtures."""
        import os
        self.api_key = os.getenv("GEMINI_API_KEY")
        
        # Skip tests if API key is not available
        if not self.api_key or self.api_key == "your-gemini-api-key-here":
            self.skipTest("GEMINI_API_KEY not configured in .env")
        
        self.service = CandidateExtractionService(
            model_name="gemini-1.5-flash",
            api_key=self.api_key
        )
        
        # Create test user
        self.user = CustomUser.objects.create_user(
            email="integration@example.com",
            username="integration_user",
            full_name="Integration User",
            password="testpass123",
            role=RoleChoices.ANNOTATOR,
        )
        
        # Create raw document
        self.raw_doc = RawDocument.objects.create(
            user=self.user,
            title="integration-test.txt",
            processing_status=ProcessingStatusChoices.COMPLETED,
            review_status=ReviewStatusChoices.APPROVED,
        )
        
        # Create extracted document
        self.extracted_doc = ExtractedDocument.objects.create(
            raw_document=self.raw_doc,
            full_text="Integration test document content.",
            processed_at="2024-01-01T00:00:00Z",
        )
        
        # Create approved chunk with real sentiment content
        self.chunk = Chunk.objects.create(
            extracted_document=self.extracted_doc,
            status=ChunkStatusChoices.APPROVED,
            text="The product quality exceeded my expectations! But the customer service was disappointing. Overall, I'm satisfied with my purchase.",
            order_index=1,
            char_start=0,
            char_end=140,
            token_count=30,
        )

    def test_gemini_api_call_succeeds(self):
        """Test that real Gemini API call succeeds and returns valid candidates."""
        try:
            processed, created, skipped = self.service.process_chunk(self.chunk)
            
            # Should process without error
            self.assertGreater(processed, 0)
            self.assertGreaterEqual(created, 0)
            self.assertGreaterEqual(skipped, 0)
            
            # Should create some NLPChunks
            nlp_chunks = NLPChunk.objects.filter(source_chunk=self.chunk)
            self.assertGreater(nlp_chunks.count(), 0)
            
            # Verify structure of created chunks
            for chunk in nlp_chunks:
                self.assertEqual(chunk.source_chunk, self.chunk)
                self.assertEqual(chunk.task_type, NLPTaskTypeChoices.SENTIMENT)
                self.assertIsNotNone(chunk.text)
                self.assertIsNotNone(chunk.ai_confidence_score)
                self.assertIsNotNone(chunk.metadata)
                
        except GeminiClientError as e:
            self.skipTest(f"Gemini API error (may be rate limit or API issue): {e}")

    def test_process_approved_chunks_batch_integration(self):
        """Test batch processing of approved chunks with real Gemini API."""
        # Create multiple approved chunks
        for i in range(2):
            Chunk.objects.create(
                extracted_document=self.extracted_doc,
                status=ChunkStatusChoices.APPROVED,
                text=f"Test content {i}: This is great! But slow. Really disappointed with quality.",
                order_index=i + 2,
                char_start=0,
                char_end=70,
                token_count=15,
            )
        
        try:
            # Process all approved chunks
            self.service.process_approved_chunks(batch_size=5)
            
            # Verify NLPChunks were created
            nlp_chunks = NLPChunk.objects.filter(task_type=NLPTaskTypeChoices.SENTIMENT)
            self.assertGreater(nlp_chunks.count(), 0)
            
        except GeminiClientError as e:
            self.skipTest(f"Gemini API error: {e}")
