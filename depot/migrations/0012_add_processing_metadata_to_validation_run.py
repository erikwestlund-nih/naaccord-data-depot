# Generated manually for granular validation system
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('depot', '0011_create_validation_pipeline_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='validationrun',
            name='processing_metadata',
            field=models.JSONField(blank=True, help_text='Metadata about data processing transformations applied (column renames, value remaps, data cleaning, etc.)', null=True),
        ),
    ]
