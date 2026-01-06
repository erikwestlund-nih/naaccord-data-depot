"""
Central configuration for NA-ACCORD data table names and ordering.
This module provides the single source of truth for table display names and ordering.
"""

# Table definitions mapping internal names to display names
TABLE_DEFINITIONS = {
    'patient': 'Patient Record',
    'diagnosis': 'Diagnosis Record',
    'laboratory': 'Laboratory Test Results Record',
    'medication': 'Medication Records',
    'medication_administration': 'Medication Administration (LAI ART)',
    'mortality': 'Cause of Death Record',
    'geography': 'Geographic Data',
    'encounter': 'Encounter Information',
    'insurance': 'Insurance Information',
    'hospitalization': 'Hospitalizations',
    'substance_survey': 'Substance Use Survey Information',
    'mental_health_survey': 'Mental Health Survey Data',
    'procedure': 'Procedures',
    'discharge_dx': 'Discharge Diagnosis Data',
    'risk_factor': 'HIV Acquisition Risk Factor Record',
    'census': 'Census',
}

# Canonical order for table display
TABLE_ORDER = [
    'patient',
    'diagnosis',
    'laboratory',
    'medication',
    'medication_administration',
    'mortality',
    'geography',
    'encounter',
    'insurance',
    'hospitalization',
    'substance_survey',
    'mental_health_survey',
    'procedure',
    'discharge_dx',
    'risk_factor',
    'census',
]

# Tables that require patient file to be uploaded first
TABLES_REQUIRING_PATIENT = [
    'diagnosis',
    'laboratory',
    'medication',
    'medication_administration',
    'mortality',
    'geography',
    'encounter',
    'insurance',
    'hospitalization',
    'substance_survey',
    'mental_health_survey',
    'procedure',
    'discharge_dx',
    'risk_factor',
    'census',
]


def get_table_display_name(internal_name):
    """
    Get the display name for a table given its internal name.
    
    Args:
        internal_name: The internal table name (e.g., 'patient')
    
    Returns:
        The display name with " table" suffix (e.g., 'Patient Record table')
    """
    display_name = TABLE_DEFINITIONS.get(internal_name, internal_name)
    return f"{display_name} table"


def get_table_order_index(internal_name):
    """
    Get the order index for a table.
    
    Args:
        internal_name: The internal table name
    
    Returns:
        The order index (0-based) or 999 if not found
    """
    try:
        return TABLE_ORDER.index(internal_name)
    except ValueError:
        return 999


def requires_patient_file(internal_name):
    """
    Check if a table requires the patient file to be uploaded first.
    
    Args:
        internal_name: The internal table name
    
    Returns:
        True if the table requires patient file, False otherwise
    """
    return internal_name in TABLES_REQUIRING_PATIENT


def get_ordered_tables():
    """
    Get all tables in their canonical order with display names.
    
    Returns:
        List of tuples: [(internal_name, display_name), ...]
    """
    return [(name, get_table_display_name(name)) for name in TABLE_ORDER]


def is_patient_table(internal_name):
    """
    Check if a table is the patient table.
    
    Args:
        internal_name: The internal table name
    
    Returns:
        True if this is the patient table, False otherwise
    """
    return internal_name.lower() == 'patient'