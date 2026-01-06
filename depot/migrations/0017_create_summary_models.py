from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('depot', '0016_add_processed_file_path'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubmissionSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('total_tables', models.IntegerField(default=0)),
                ('tables_validated', models.IntegerField(default=0)),
                ('tables_with_errors', models.IntegerField(default=0)),
                ('tables_with_warnings', models.IntegerField(default=0)),
                ('overall_completeness_pct', models.FloatField(default=0.0)),
                ('overall_validity_pct', models.FloatField(default=0.0)),
                ('total_rows', models.IntegerField(default=0)),
                ('total_variables', models.IntegerField(default=0)),
                ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='summary_stats', to='depot.cohortsubmission')),
                ('validation_state', models.OneToOneField(blank=True, help_text='Optional link back to validation status tracking', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='statistics', to='depot.submissionvalidation')),
            ],
            options={
                'db_table': 'depot_submission_summaries',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VariableSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('total_count', models.IntegerField(default=0)),
                ('unique_count', models.IntegerField(default=0)),
                ('null_count', models.IntegerField(default=0)),
                ('empty_count', models.IntegerField(default=0)),
                ('valid_count', models.IntegerField(default=0)),
                ('invalid_count', models.IntegerField(default=0)),
                ('warning_count', models.IntegerField(default=0)),
                ('error_count', models.IntegerField(default=0)),
                ('mean_value', models.FloatField(blank=True, null=True)),
                ('median_value', models.FloatField(blank=True, null=True)),
                ('min_value', models.FloatField(blank=True, null=True)),
                ('max_value', models.FloatField(blank=True, null=True)),
                ('std_dev', models.FloatField(blank=True, null=True)),
                ('mode_value', models.CharField(blank=True, max_length=255, null=True)),
                ('mode_count', models.IntegerField(blank=True, null=True)),
                ('chart_data', models.JSONField(blank=True, default=dict)),
                ('example_values', models.JSONField(blank=True, default=list)),
                ('validation_variable', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='summary_stats', to='depot.validationvariable')),
            ],
            options={
                'db_table': 'depot_variable_summaries',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DataTableSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('total_variables', models.IntegerField(default=0)),
                ('variables_validated', models.IntegerField(default=0)),
                ('variables_with_issues', models.IntegerField(default=0)),
                ('variables_with_warnings', models.IntegerField(default=0)),
                ('overall_completeness_pct', models.FloatField(default=0.0)),
                ('overall_validity_pct', models.FloatField(default=0.0)),
                ('total_rows', models.IntegerField(default=0)),
                ('total_columns', models.IntegerField(default=0)),
                ('last_variable_validated_at', models.DateTimeField(blank=True, null=True)),
                ('validation_run', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='summary_stats', to='depot.validationrun')),
            ],
            options={
                'db_table': 'depot_datatable_summaries',
                'ordering': ['-created_at'],
            },
        ),
    ]
