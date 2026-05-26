from apps.processing.services.ai_qc_service import AIQualityCheckService
import sys
import os
import django

# Setup Django environment

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()


if __name__ == "__main__":
    batch_size = 100
    if len(sys.argv) > 1:
        try:
            batch_size = int(sys.argv[1])
        except Exception:
            print("Invalid batch size argument, using default 100.")
    processed = AIQualityCheckService().process_pending_chunks(batch_size=batch_size)
    print(f"AI QC completed: processed {processed} chunks.")
