"""
Granular Validation System Package.

This package implements a job-based validation architecture that replaces
the monolithic Quarto notebook approach with independent, parallel validations.

Key Components:
- ValidationRun: Orchestrates multiple validation jobs
- ValidationJob: Individual validation tasks with progress tracking
- ValidationIssue: Specific problems found during validation
- BaseValidator: Base class for all validators
- VALIDATION_REGISTRY: Central registry of available validators

See: docs/technical/granular-validation-system.md
"""

from depot.validation.base import BaseValidator
from depot.validation.registry import VALIDATION_REGISTRY, get_enabled_validators

__all__ = [
    'BaseValidator',
    'VALIDATION_REGISTRY',
    'get_enabled_validators',
]
