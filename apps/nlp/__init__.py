"""
NLP Annotation Pipeline App

Secondary NLP annotation pipeline for transforming QC-approved chunks
into NLP-task-ready annotation units.

Separate from:
- Quality control annotation (QC pipeline)
- Processing app (document extraction, chunking, consensus)
- Dataset marketplace (selling, payments, publishing)

Supports multiple NLP task types:
- Sentiment Analysis
- Named Entity Recognition (NER)
- Topic Classification
- Intent Detection
- Toxicity Classification
- Future extensible NLP tasks
"""

default_app_config = "apps.nlp.apps.NlpConfig"
