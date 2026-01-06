"""
Validator Library

Column-level validators for data validation system.

Each validator checks one rule for one column and returns a ValidationResult.
Validators are PHI-aware and never store patient IDs with values.

Available validators:
- no_duplicates: Check for duplicate values in a column

Usage:
    from depot.validators import get_validator

    validator = get_validator("no_duplicates")
    result = validator.execute(conn, "data", "cohortPatientId", {})
"""

from .base import BaseValidator, ValidationResult, ValidatorException
from .no_duplicates import NoDuplicatesValidator

# Validator registry
VALIDATOR_REGISTRY = {
    'no_duplicates': NoDuplicatesValidator,
}


def get_validator(rule_key: str) -> BaseValidator:
    """
    Get validator instance by rule key.

    Args:
        rule_key: Validator identifier (e.g., "no_duplicates")

    Returns:
        Validator instance

    Raises:
        ValueError: If validator not found
    """
    validator_class = VALIDATOR_REGISTRY.get(rule_key)
    if validator_class is None:
        raise ValueError(f"Unknown validator: {rule_key}")

    return validator_class()


def list_validators():
    """
    Get list of available validator rule keys.

    Returns:
        List of rule key strings
    """
    return list(VALIDATOR_REGISTRY.keys())


__all__ = [
    'BaseValidator',
    'ValidationResult',
    'ValidatorException',
    'get_validator',
    'list_validators',
    'NoDuplicatesValidator',
]
