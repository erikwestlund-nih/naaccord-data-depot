# Generated migration for patient ID validation rejection fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('depot', '0019_add_upload_validation_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='datatablefile',
            name='rejection_reason',
            field=models.TextField(
                blank=True,
                help_text='Reason why file was rejected (e.g., invalid patient IDs)',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='datatablefile',
            name='rejection_details',
            field=models.JSONField(
                blank=True,
                help_text='Structured rejection data including invalid IDs and metadata',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='datatablefile',
            name='rejected_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When file was rejected',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='datatablefile',
            name='files_cleaned_up',
            field=models.BooleanField(
                default=False,
                help_text='Whether all PHI files have been deleted after rejection'
            ),
        ),
        migrations.AddField(
            model_name='datatablefile',
            name='cleanup_verified_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When file cleanup was verified',
                null=True
            ),
        ),
        migrations.AlterField(
            model_name='cohortsubmissiondatatable',
            name='status',
            field=models.CharField(
                choices=[
                    ('not_started', 'Not Started'),
                    ('in_progress', 'In Progress'),
                    ('completed', 'Completed'),
                    ('rejected', 'Rejected'),
                    ('not_available', 'Not Available'),
                ],
                default='not_started',
                help_text='Current status of this data table in the submission',
                max_length=20
            ),
        ),
    ]
