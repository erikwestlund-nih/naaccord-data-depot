"""
Base Validator Abstract Class

Defines the interface for all column validators in the validation system.

Architecture:
- Each validator checks one rule for one column
- Returns ValidationResult with pass/fail, message, affected rows
- PHI-aware: never stores patient IDs with values
- Severity levels: warning or error

Usage:
    class MyValidator(BaseValidator):
        def validate(self, conn, table_name, column_name, params):
            # Implementation
            return ValidationResult(...)

    validator = MyValidator()
    result = validator.execute(conn, "data", "cohortPatientId", {"min": 1})
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Result of a validation check.

    Attributes:
        passed: Whether validation passed
        rule_key: Validator identifier (e.g., "no_duplicates")
        rule_params: Parameters used for validation
        severity: "warning" or "error"
        message: Human-readable validation message
        affected_row_count: Number of rows with issues
        row_numbers: List of row numbers (1-indexed, PHI-safe)
        invalid_value: Example invalid value (only if not PHI-sensitive)
        meta: Additional validator-specific metadata
    """
    passed: bool
    rule_key: str
    rule_params: Dict[str, Any]
    severity: str
    message: str
    affected_row_count: int = 0
    row_numbers: List[int] = None
    invalid_value: Optional[str] = None
    meta: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize default values."""
        if self.row_numbers is None:
            self.row_numbers = []
        if self.meta is None:
            self.meta = {}


class BaseValidator(ABC):
    """
    Abstract base class for all validators.

    Subclasses must implement validate() method to perform
    the actual validation logic.
    """

    # Class attributes for validator metadata
    rule_key: str = None  # Must be set by subclass
    default_severity: str = "warning"  # Can be overridden
    requires_params: List[str] = []  # Required parameter names

    def __init__(self):
        """Initialize validator."""
        if self.rule_key is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define 'rule_key' class attribute"
            )

    @abstractmethod
    def validate(
        self,
        conn,
        table_name: str,
        column_name: str,
        params: Dict[str, Any]
    ) -> ValidationResult:
        """
        Perform validation check on a column.

        Args:
            conn: DuckDB connection
            table_name: Name of table to validate
            column_name: Name of column to validate
            params: Validator parameters from definition

        Returns:
            ValidationResult with check outcome

        Raises:
            ValidatorException: If validation fails to execute
        """
        pass

    def execute(
        self,
        conn,
        table_name: str,
        column_name: str,
        params: Dict[str, Any]
    ) -> ValidationResult:
        """
        Execute validation with parameter checking and error handling.

        Args:
            conn: DuckDB connection
            table_name: Name of table to validate
            column_name: Name of column to validate
            params: Validator parameters from definition

        Returns:
            ValidationResult with check outcome
        """
        try:
            # Validate required parameters
            missing_params = [
                p for p in self.requires_params
                if p not in params
            ]
            if missing_params:
                return ValidationResult(
                    passed=False,
                    rule_key=self.rule_key,
                    rule_params=params,
                    severity="error",
                    message=f"Missing required parameters: {', '.join(missing_params)}",
                    meta={'error_type': 'missing_parameters'}
                )

            # Execute validation
            logger.debug(
                f"Executing {self.rule_key} on {column_name} "
                f"with params {params}"
            )

            result = self.validate(conn, table_name, column_name, params)

            # Ensure rule metadata is set
            if result.rule_key != self.rule_key:
                result.rule_key = self.rule_key
            if not result.rule_params:
                result.rule_params = params
            if not result.severity:
                result.severity = params.get('severity', self.default_severity)

            return result

        except Exception as e:
            logger.error(
                f"Validator {self.rule_key} failed on {column_name}: {e}",
                exc_info=True
            )

            return ValidationResult(
                passed=False,
                rule_key=self.rule_key,
                rule_params=params,
                severity="error",
                message=f"Validator execution failed: {str(e)}",
                meta={'error_type': 'execution_failure', 'error': str(e)}
            )

    def _get_row_numbers(
        self,
        conn,
        table_name: str,
        where_clause: str,
        limit: int = 1000
    ) -> List[int]:
        """
        Get row numbers (1-indexed) matching a WHERE clause.

        Args:
            conn: DuckDB connection
            table_name: Name of table
            where_clause: SQL WHERE condition (without WHERE keyword)
            limit: Maximum number of row numbers to return

        Returns:
            List of row numbers (1-indexed)
        """
        try:
            query = f"""
                SELECT row_number() OVER () as row_num
                FROM {table_name}
                WHERE {where_clause}
                LIMIT {limit}
            """

            result = conn.execute(query).fetchall()
            return [row[0] for row in result]

        except Exception as e:
            logger.warning(f"Failed to get row numbers: {e}")
            return []

    def _count_rows(
        self,
        conn,
        table_name: str,
        where_clause: str
    ) -> int:
        """
        Count rows matching a WHERE clause.

        Args:
            conn: DuckDB connection
            table_name: Name of table
            where_clause: SQL WHERE condition (without WHERE keyword)

        Returns:
            Row count
        """
        try:
            query = f"""
                SELECT COUNT(*)
                FROM {table_name}
                WHERE {where_clause}
            """

            result = conn.execute(query).fetchone()
            return result[0] if result else 0

        except Exception as e:
            logger.warning(f"Failed to count rows: {e}")
            return 0

    def _get_sample_value(
        self,
        conn,
        table_name: str,
        column_name: str,
        where_clause: str
    ) -> Optional[str]:
        """
        Get a sample value matching a WHERE clause.

        Args:
            conn: DuckDB connection
            table_name: Name of table
            column_name: Name of column
            where_clause: SQL WHERE condition (without WHERE keyword)

        Returns:
            Sample value as string or None
        """
        try:
            query = f"""
                SELECT "{column_name}"
                FROM {table_name}
                WHERE {where_clause}
                LIMIT 1
            """

            result = conn.execute(query).fetchone()
            return str(result[0]) if result else None

        except Exception as e:
            logger.warning(f"Failed to get sample value: {e}")
            return None

    def __str__(self):
        """String representation of validator."""
        return f"{self.__class__.__name__}(rule_key='{self.rule_key}')"


class ValidatorException(Exception):
    """Raised when validator execution fails."""
    pass
