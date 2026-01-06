"""
Validator registry for granular validation system.

This registry defines all available validation types and their configurations.
Validators are registered here and can be executed in parallel or with dependencies.

To add a new validator:
1. Create validator class inheriting from BaseValidator
2. Add entry to VALIDATION_REGISTRY dict below
3. Validator will automatically be picked up by validation orchestration

See: docs/technical/granular-validation-system.md
"""

# Import validators as they are implemented
# from depot.validation.validators.required_fields import RequiredFieldValidator
# from depot.validation.validators.date_ranges import DateRangeValidator
# from depot.validation.validators.enum_values import EnumValueValidator
from depot.validation.validators.patient_ids import PatientIDValidator


# Validation Registry
# Each entry defines a validation type with its configuration
VALIDATION_REGISTRY = {
    'patient_ids': {
        'validator': PatientIDValidator,
        'display_name': 'Patient ID Validation',
        'description': 'Validates patient IDs against submission master list',
        'dependencies': [],  # No dependencies
        'parallel_safe': True,  # Can run in parallel with other validations
        'enabled': True,  # Can be disabled per file type
        'priority': 1,  # Lower numbers run first
    },

    # TODO: Implement these validators
    # 'required_fields': {
    #     'validator': RequiredFieldValidator,
    #     'display_name': 'Required Fields Check',
    #     'description': 'Validates that all required fields have values',
    #     'dependencies': [],
    #     'parallel_safe': True,
    #     'enabled': True,
    #     'priority': 1,
    # },
    #
    # 'date_ranges': {
    #     'validator': DateRangeValidator,
    #     'display_name': 'Date Range Validation',
    #     'description': 'Validates date fields are within acceptable ranges',
    #     'dependencies': [],
    #     'parallel_safe': True,
    #     'enabled': True,
    #     'priority': 2,
    # },
    #
    # 'enum_values': {
    #     'validator': EnumValueValidator,
    #     'display_name': 'Categorical Value Check',
    #     'description': 'Validates enum/categorical field values',
    #     'dependencies': [],
    #     'parallel_safe': True,
    #     'enabled': True,
    #     'priority': 2,
    # },
    #
    # 'data_types': {
    #     'validator': DataTypeValidator,
    #     'display_name': 'Data Type Validation',
    #     'description': 'Validates data types match definition',
    #     'dependencies': [],
    #     'parallel_safe': True,
    #     'enabled': True,
    #     'priority': 1,
    # },
    #
    # 'cross_file_consistency': {
    #     'validator': CrossFileValidator,
    #     'display_name': 'Cross-File Consistency',
    #     'description': 'Validates consistency across multiple files',
    #     'dependencies': ['patient_ids'],  # Depends on patient ID validation
    #     'parallel_safe': False,  # Requires other files to be processed
    #     'enabled': True,
    #     'priority': 10,  # Run last
    # },
}


def get_enabled_validators():
    """
    Get list of enabled validator keys.

    Returns:
        List[str]: Keys of enabled validators
    """
    return [key for key, config in VALIDATION_REGISTRY.items() if config.get('enabled', True)]


def get_validator_config(validation_type: str):
    """
    Get configuration for a specific validator.

    Args:
        validation_type: Key from VALIDATION_REGISTRY

    Returns:
        dict: Validator configuration

    Raises:
        KeyError: If validation_type not found
    """
    return VALIDATION_REGISTRY[validation_type]


def get_parallel_validators():
    """
    Get list of validators that can run in parallel (no dependencies).

    Returns:
        List[str]: Keys of parallel-safe validators
    """
    return [
        key for key, config in VALIDATION_REGISTRY.items()
        if config.get('parallel_safe', False) and not config.get('dependencies', [])
    ]


def get_dependent_validators():
    """
    Get list of validators that have dependencies.

    Returns:
        List[str]: Keys of validators with dependencies
    """
    return [
        key for key, config in VALIDATION_REGISTRY.items()
        if config.get('dependencies', [])
    ]


def get_validators_by_priority():
    """
    Get validators sorted by priority (lower numbers first).

    Returns:
        List[Tuple[str, dict]]: List of (key, config) tuples sorted by priority
    """
    items = list(VALIDATION_REGISTRY.items())
    return sorted(items, key=lambda x: x[1].get('priority', 999))
