from django.db import migrations


def forwards(apps, schema_editor):
    # Map existing 'news' domain values to 'politics' across relevant models
    try:
        RawDocument = apps.get_model("documents", "RawDocument")
        RawDocument.objects.filter(domain="news").update(domain="politics")
    except LookupError:
        pass

    try:
        Dataset = apps.get_model("datasets", "Dataset")
        Dataset.objects.filter(domain="news").update(domain="politics")
    except LookupError:
        pass

    try:
        AnnotationTask = apps.get_model("processing", "AnnotationTask")
        AnnotationTask.objects.filter(domain="news").update(domain="politics")
    except LookupError:
        pass

    try:
        ExpertTask = apps.get_model("processing", "ExpertTask")
        ExpertTask.objects.filter(domain="news").update(domain="politics")
    except LookupError:
        pass

    try:
        NLPChunk = apps.get_model("nlp", "NLPChunk")
        if hasattr(NLPChunk, "source_domain"):
            NLPChunk.objects.filter(source_domain="news").update(source_domain="politics")
    except LookupError:
        pass


def backwards(apps, schema_editor):
    # Revert mapping if necessary
    try:
        RawDocument = apps.get_model("documents", "RawDocument")
        RawDocument.objects.filter(domain="politics").update(domain="news")
    except LookupError:
        pass

    try:
        Dataset = apps.get_model("datasets", "Dataset")
        Dataset.objects.filter(domain="politics").update(domain="news")
    except LookupError:
        pass

    try:
        AnnotationTask = apps.get_model("processing", "AnnotationTask")
        AnnotationTask.objects.filter(domain="politics").update(domain="news")
    except LookupError:
        pass

    try:
        ExpertTask = apps.get_model("processing", "ExpertTask")
        ExpertTask.objects.filter(domain="politics").update(domain="news")
    except LookupError:
        pass

    try:
        NLPChunk = apps.get_model("nlp", "NLPChunk")
        if hasattr(NLPChunk, "source_domain"):
            NLPChunk.objects.filter(source_domain="politics").update(source_domain="news")
    except LookupError:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0005_alter_rawdocument_domain"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
