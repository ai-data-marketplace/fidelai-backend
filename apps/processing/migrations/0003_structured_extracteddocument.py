from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processing', '0002_chunk_status_chunk_processing__status_3ccf51_idx'),
    ]

    operations = [
        migrations.RenameField(
            model_name='extracteddocument',
            old_name='extracted_text',
            new_name='full_text',
        ),
        migrations.RenameField(
            model_name='extracteddocument',
            old_name='extraction_metadata',
            new_name='layout_metadata',
        ),
        migrations.AddField(
            model_name='extracteddocument',
            name='structure',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='extracteddocument',
            name='language_detected',
            field=models.CharField(default='amharic', max_length=32),
        ),
        migrations.AddField(
            model_name='extracteddocument',
            name='confidence_score',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=5),
        ),
        migrations.AddIndex(
            model_name='extracteddocument',
            index=models.Index(fields=['language_detected'], name='processing_langua_b8d7c6_idx'),
        ),
    ]