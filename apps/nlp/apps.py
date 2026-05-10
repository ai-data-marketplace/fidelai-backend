"""
Django app configuration for NLP app.
"""

from django.apps import AppConfig


class NlpConfig(AppConfig):
    """Configuration for the NLP app."""
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nlp"
    verbose_name = "NLP Annotation Pipeline"
    
    def ready(self):
        """Initialize app."""
        # Import signals if needed
        # from apps.nlp import signals  # noqa
        pass
