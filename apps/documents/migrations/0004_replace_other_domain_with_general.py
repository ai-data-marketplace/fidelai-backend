from django.db import migrations


def forwards(apps, schema_editor):
	models_to_update = [
		("documents", "RawDocument"),
		("datasets", "Dataset"),
		("processing", "AnnotationTask"),
		("processing", "ExpertTask"),
	]

	for app_label, model_name in models_to_update:
		model = apps.get_model(app_label, model_name)
		model.objects.filter(domain="other").update(domain="general")


def backwards(apps, schema_editor):
	models_to_update = [
		("documents", "RawDocument"),
		("datasets", "Dataset"),
		("processing", "AnnotationTask"),
		("processing", "ExpertTask"),
	]

	for app_label, model_name in models_to_update:
		model = apps.get_model(app_label, model_name)
		model.objects.filter(domain="general").update(domain="other")


class Migration(migrations.Migration):

	dependencies = [
		("documents", "0003_add_validation_notes_to_rawdocument"),
		("datasets", "0002_dataset_approved_at_dataset_approved_by_and_more"),
		("processing", "0011_extracteddocument_similarity_signature"),
	]

	operations = [
		migrations.RunPython(forwards, backwards),
	]