# Generated migration to standardize all DataFileType names to snake_case
# This ensures database names match definition file naming convention

from django.db import migrations


def fix_all_camelcase_names(apps, schema_editor):
    """Update all camelCase DataFileType names to snake_case to match definition files."""
    DataFileType = apps.get_model('depot', 'DataFileType')

    # Mapping of old camelCase names to new snake_case names
    name_fixes = {
        'dischargeDx': 'discharge_dx',
        'geographic': 'geography',
        'medicationAdministration': 'medication_administration',
        'MHSurvey': 'mental_health_survey',
        'substanceSurvey': 'substance_survey',
        'riskFactor': 'risk_factor',  # In case this migration runs before previous fix
    }

    total_updated = 0
    for old_name, new_name in name_fixes.items():
        updated = DataFileType.objects.filter(name=old_name).update(name=new_name)
        if updated:
            print(f"  Updated {updated} record(s): '{old_name}' → '{new_name}'")
            total_updated += updated

    if total_updated:
        print(f"\n✅ Successfully updated {total_updated} DataFileType record(s) to snake_case")
    else:
        print("No camelCase records found (may already be updated)")


def reverse_fix(apps, schema_editor):
    """Reverse the migration (snake_case → camelCase)."""
    DataFileType = apps.get_model('depot', 'DataFileType')

    # Reverse mapping
    name_fixes = {
        'discharge_dx': 'dischargeDx',
        'geography': 'geographic',
        'medication_administration': 'medicationAdministration',
        'mental_health_survey': 'MHSurvey',
        'substance_survey': 'substanceSurvey',
        'risk_factor': 'riskFactor',
    }

    total_updated = 0
    for old_name, new_name in name_fixes.items():
        updated = DataFileType.objects.filter(name=old_name).update(name=new_name)
        if updated:
            print(f"  Reverted {updated} record(s): '{old_name}' → '{new_name}'")
            total_updated += updated

    if total_updated:
        print(f"\nReverted {total_updated} DataFileType record(s) to camelCase")


class Migration(migrations.Migration):

    dependencies = [
        ('depot', '0020_add_rejection_fields'),
    ]

    operations = [
        migrations.RunPython(fix_all_camelcase_names, reverse_fix),
    ]
