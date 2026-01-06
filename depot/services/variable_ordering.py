"""
Variable ordering service for validation displays.

Provides functionality to:
1. Order variables according to data table definitions
2. Separate core (cohort data model) variables from additional variables
3. Maintain consistent ordering across the application
"""
import logging
from typing import List, Dict, Tuple
from depot.services.definition_processing import DefinitionProcessingService

logger = logging.getLogger(__name__)


class VariableOrderingService:
    """Service for ordering validation variables in a consistent, meaningful way."""

    def __init__(self, data_file_type_name: str):
        """
        Initialize the ordering service for a specific data file type.

        Args:
            data_file_type_name: Name of the data file type (e.g., 'patient', 'diagnosis')
        """
        self.data_file_type_name = data_file_type_name
        self.definition_service = DefinitionProcessingService(data_file_type_name)
        self._core_variable_order = None
        self._load_variable_order()

    def _load_variable_order(self):
        """Load the variable order from the definition file."""
        try:
            definition = self.definition_service.load_definition()
            # Extract variable names in the order they appear in the definition
            self._core_variable_order = [
                var['name'] for var in definition.get('variables', [])
                if 'name' in var
            ]
            # Create lowercase mapping for case-insensitive lookups
            self._core_variable_order_lower = {name.lower(): idx for idx, name in enumerate(self._core_variable_order)}
            logger.info(f"Loaded {len(self._core_variable_order)} core variables for {self.data_file_type_name}")
        except Exception as e:
            logger.error(f"Failed to load variable order for {self.data_file_type_name}: {e}", exc_info=True)
            self._core_variable_order = []
            self._core_variable_order_lower = {}

    def is_core_variable(self, variable_name: str) -> bool:
        """
        Check if a variable is a core variable (in the cohort data model).
        Uses case-insensitive matching.

        Args:
            variable_name: Name of the variable to check

        Returns:
            True if the variable is in the core definition, False otherwise
        """
        return variable_name.lower() in self._core_variable_order_lower

    def get_variable_order_index(self, variable_name: str) -> int:
        """
        Get the order index for a variable.
        Uses case-insensitive matching.

        Args:
            variable_name: Name of the variable

        Returns:
            Order index (lower is earlier). Non-core variables get high indices.
        """
        return self._core_variable_order_lower.get(variable_name.lower(), 999999)

    def order_variables(self, variables: List) -> Tuple[List, List]:
        """
        Order variables into core and additional groups.

        Args:
            variables: List of ValidationVariable objects or dicts with 'column_name'

        Returns:
            Tuple of (core_variables, additional_variables), both ordered appropriately
        """
        # Separate into core and additional
        core_vars = []
        additional_vars = []

        for var in variables:
            # Handle both model objects and dicts
            if hasattr(var, 'column_name'):
                var_name = var.column_name
            else:
                var_name = var.get('column_name')

            if var_name and self.is_core_variable(var_name):
                core_vars.append(var)
            else:
                additional_vars.append(var)

        # Sort core variables by definition order
        def get_var_name(v):
            return v.column_name if hasattr(v, 'column_name') else v.get('column_name')

        core_vars.sort(key=lambda v: self.get_variable_order_index(get_var_name(v)))

        # Sort additional variables alphabetically
        additional_vars.sort(key=lambda v: get_var_name(v).lower())

        return core_vars, additional_vars

    def order_all_variables(self, variables: List) -> List:
        """
        Order all variables with core variables first, then additional.

        Args:
            variables: List of ValidationVariable objects or dicts

        Returns:
            Ordered list of variables
        """
        core_vars, additional_vars = self.order_variables(variables)
        return core_vars + additional_vars
