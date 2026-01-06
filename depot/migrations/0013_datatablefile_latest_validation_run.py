from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('depot', '0012_add_processing_metadata_to_validation_run'),
    ]

    operations = [
        migrations.AddField(
            model_name='datatablefile',
            name='latest_validation_run',
            field=models.ForeignKey(
                blank=True,
                help_text='Most recent granular validation run for this file',
                null=True,
                on_delete=models.SET_NULL,
                related_name='latest_files',
                to='depot.validationrun',
            ),
        ),
    ]
