"""
Definition Processing Service

Loads and processes JSON data definitions for validation.

Architecture:
- Reads JSON definition files from depot/data/definitions/
- Extracts variable definitions with validators
- Provides structured data for creating ValidationVariable records

Usage:
    service = DefinitionProcessingService("patient")
    definition = service.load_definition()
    variables = service.get_variables_for_validation()
    # Returns list of dicts with column_name, column_type, validators, etc.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class DefinitionNotFoundException(Exception):
    """Raised when definition file is not found."""
    pass


class DefinitionParseException(Exception):
    """Raised when definition file cannot be parsed."""
    pass


class DefinitionProcessingService:
    """
    Service for loading and processing data definitions.

    Reads JSON definition files and extracts validation rules
    and metadata for creating ValidationVariable records.
    """

    def __init__(self, data_file_type_name: str):
        """
        Initialize definition processing service.

        Args:
            data_file_type_name: Name of data file type (e.g., "patient", "visit")
        """
        self.data_file_type_name = data_file_type_name
        self.definitions_dir = Path(settings.BASE_DIR) / "depot" / "data" / "definitions"
        self.definition: Optional[Dict] = None

    def load_definition(self) -> Dict:
        """
        Load JSON definition file for data file type.

        Returns:
            Parsed definition dictionary

        Raises:
            DefinitionNotFoundException: If definition file not found
            DefinitionParseException: If definition cannot be parsed
        """
        # Try standard naming first (patient.json)
        definition_path = self.definitions_dir / f"{self.data_file_type_name}.json"

        # Fall back to _definition.json naming (patient_definition.json)
        if not definition_path.exists():
            definition_path = self.definitions_dir / f"{self.data_file_type_name}_definition.json"

        if not definition_path.exists():
            raise DefinitionNotFoundException(
                f"Definition file not found: {definition_path}"
            )

        try:
            with open(definition_path, 'r') as f:
                loaded_data = json.load(f)

            # Handle both formats: array of variables or dict with 'variables' key
            if isinstance(loaded_data, list):
                # Legacy format: array of variable definitions
                self.definition = {
                    'variables': loaded_data,
                    'version': '1.0',
                    'description': f'{self.data_file_type_name} data definition'
                }
            else:
                # New format: dict with 'variables' key
                self.definition = loaded_data

            logger.info(f"Loaded definition from {definition_path}")
            return self.definition

        except json.JSONDecodeError as e:
            raise DefinitionParseException(
                f"Failed to parse definition {definition_path}: {e}"
            )

    def get_variables_for_validation(self) -> List[Dict]:
        """
        Extract variable definitions for validation processing.

        Returns:
            List of variable definition dicts, each containing:
                - column_name: Variable name
                - column_type: Data type (string, int, date, etc.)
                - display_name: Human-readable name
                - validators: List of validator definitions
                - required: Whether value is required
                - phi_sensitive: Whether column contains PHI

        Raises:
            DefinitionParseException: If definition not loaded or invalid
        """
        if self.definition is None:
            self.load_definition()

        if 'variables' not in self.definition:
            raise DefinitionParseException(
                f"Definition missing 'variables' key for {self.data_file_type_name}"
            )

        variables = []

        for var_def in self.definition['variables']:
            # Extract basic fields
            column_name = var_def.get('name')
            if not column_name:
                logger.warning("Variable definition missing 'name', skipping")
                continue

            # Build variable record
            variable = {
                'column_name': column_name,
                'column_type': var_def.get('type', 'string'),
                'display_name': var_def.get('label', column_name),
                'validators': self._extract_validators(var_def),
                'required': not var_def.get('value_optional', False),
                'phi_sensitive': var_def.get('phi_sensitive', False),
                'allowed_values': var_def.get('allowed_values', [])
            }

            variables.append(variable)

        logger.info(f"Extracted {len(variables)} variables for validation")
        return variables

    def _extract_validators(self, var_def: Dict) -> List[Dict]:
        """
        Extract and normalize validator definitions from variable.

        Args:
            var_def: Variable definition dict

        Returns:
            List of validator definition dicts with rule_key and rule_params
        """
        validators = []

        # Get explicit validators list
        explicit_validators = var_def.get('validators', [])
        for validator in explicit_validators:
            if isinstance(validator, str):
                # Simple validator name
                validators.append({
                    'rule_key': validator,
                    'rule_params': {}
                })
            elif isinstance(validator, dict):
                # Validator with parameters
                rule_key = validator.get('type') or validator.get('name')
                if rule_key:
                    rule_params = {k: v for k, v in validator.items()
                                   if k not in ['type', 'name']}
                    validators.append({
                        'rule_key': rule_key,
                        'rule_params': rule_params
                    })

        # Add implicit validators based on field attributes

        # Required validator
        if not var_def.get('value_optional', False):
            validators.append({
                'rule_key': 'required',
                'rule_params': {}
            })

        # Type validator
        column_type = var_def.get('type')
        if column_type:
            validators.append({
                'rule_key': f'type_is_{column_type}',
                'rule_params': {'expected_type': column_type}
            })

        # Enum validator (allowed_values)
        allowed_values = var_def.get('allowed_values')
        if allowed_values:
            validators.append({
                'rule_key': 'allowed_values',
                'rule_params': {'allowed_values': allowed_values}
            })

        return validators

    def get_variable_definition(self, column_name: str) -> Optional[Dict]:
        """
        Get definition for a specific variable.

        Args:
            column_name: Name of variable to look up

        Returns:
            Variable definition dict or None if not found

        Raises:
            DefinitionParseException: If definition not loaded
        """
        if self.definition is None:
            self.load_definition()

        variables = self.definition.get('variables', [])
        for var_def in variables:
            if var_def.get('name') == column_name:
                return var_def

        return None

    def get_definition_metadata(self) -> Dict:
        """
        Get metadata about the definition.

        Returns:
            Dict with definition metadata

        Raises:
            DefinitionParseException: If definition not loaded
        """
        if self.definition is None:
            self.load_definition()

        return {
            'data_file_type': self.data_file_type_name,
            'version': self.definition.get('version', '1.0'),
            'description': self.definition.get('description', ''),
            'variable_count': len(self.definition.get('variables', [])),
            'has_patient_id': any(
                var.get('name') == 'cohortPatientId'
                for var in self.definition.get('variables', [])
            )
        }

    def get_phi_sensitive_columns(self) -> List[str]:
        """
        Get list of PHI-sensitive column names.

        Returns:
            List of column names marked as PHI-sensitive

        Raises:
            DefinitionParseException: If definition not loaded
        """
        if self.definition is None:
            self.load_definition()

        phi_columns = []
        for var_def in self.definition.get('variables', []):
            if var_def.get('phi_sensitive', False):
                column_name = var_def.get('name')
                if column_name:
                    phi_columns.append(column_name)

        return phi_columns

    def validate_csv_columns(self, csv_columns: List[str]) -> Dict:
        """
        Validate CSV columns against definition.

        Args:
            csv_columns: List of column names from CSV file

        Returns:
            Dict with validation results:
                - missing_required: Required columns missing from CSV
                - extra_columns: Columns in CSV not in definition
                - matched_columns: Columns present in both
                - is_valid: Overall validation result

        Raises:
            DefinitionParseException: If definition not loaded
        """
        if self.definition is None:
            self.load_definition()

        # Get expected columns
        expected_vars = self.get_variables_for_validation()
        expected_columns = {var['column_name'] for var in expected_vars}
        required_columns = {
            var['column_name'] for var in expected_vars
            if var['required']
        }

        # Convert CSV columns to set
        csv_column_set = set(csv_columns)

        # Find missing required columns
        missing_required = required_columns - csv_column_set

        # Find extra columns
        extra_columns = csv_column_set - expected_columns

        # Find matched columns
        matched_columns = csv_column_set & expected_columns

        # Overall validation
        is_valid = len(missing_required) == 0

        result = {
            'missing_required': list(missing_required),
            'extra_columns': list(extra_columns),
            'matched_columns': list(matched_columns),
            'is_valid': is_valid,
            'csv_column_count': len(csv_columns),
            'expected_column_count': len(expected_columns),
            'matched_count': len(matched_columns)
        }

        if missing_required:
            logger.warning(
                f"Missing required columns: {', '.join(missing_required)}"
            )

        if extra_columns:
            logger.info(
                f"Extra columns not in definition: {', '.join(extra_columns)}"
            )

        return result
