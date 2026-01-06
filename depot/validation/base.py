"""
Base validator class for granular validation system.

All validators inherit from BaseValidator and implement the validate() method.
Validators operate on DuckDB connections for efficient data processing.

See: docs/technical/granular-validation-system.md
"""
from abc import ABC, abstractmethod
import duckdb
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class BaseValidator(ABC):
    """
    Base class for all validators.

    Each validator operates on a DuckDB connection and implements specific
    validation logic. Validators should be stateless and reusable.

    Example:
        class RequiredFieldValidator(BaseValidator):
            def validate(self, validation_job):
                # Implement validation logic
                return {
                    'passed': True,
                    'summary': {...},
                    'issues': []
                }
    """

    def __init__(self, duckdb_path: str, data_file_type, definition: Dict):
        """
        Initialize validator.

        Args:
            duckdb_path: Path to DuckDB file containing data
            data_file_type: DataFileType instance
            definition: JSON definition dict for this file type
        """
        self.duckdb_path = duckdb_path
        self.data_file_type = data_file_type
        self.definition = definition
        self.conn = None

    def connect(self):
        """
        Establish DuckDB connection.

        Uses read-only mode for safety.
        """
        try:
            self.conn = duckdb.connect(self.duckdb_path, read_only=True)
            logger.info(f"Connected to DuckDB: {self.duckdb_path}")
        except Exception as e:
            logger.error(f"Failed to connect to DuckDB {self.duckdb_path}: {e}")
            raise

    def disconnect(self):
        """Close DuckDB connection"""
        if self.conn:
            try:
                self.conn.close()
                logger.info(f"Disconnected from DuckDB: {self.duckdb_path}")
            except Exception as e:
                logger.warning(f"Error closing DuckDB connection: {e}")
            finally:
                self.conn = None

    @abstractmethod
    def validate(self, validation_job) -> Dict[str, Any]:
        """
        Execute validation logic.

        Subclasses must implement this method to perform specific validation.
        Use update_progress() to report progress during long-running validations.

        Args:
            validation_job: ValidationJob instance to update with progress

        Returns:
            Dict with:
                - passed: bool - Whether validation passed
                - summary: Dict - Summary statistics/counts
                - issues: List[Dict] - List of issue dicts for ValidationIssue creation
                - details: Dict (optional) - Additional details

        Example return value:
            {
                'passed': False,
                'summary': {
                    'total_rows': 10000,
                    'invalid_count': 5,
                    'valid_count': 9995
                },
                'issues': [
                    {
                        'severity': 'error',
                        'row_number': 42,
                        'column_name': 'birthDate',
                        'issue_type': 'required_field_missing',
                        'message': 'Required field "birthDate" is missing',
                        'invalid_value': None,
                        'expected_value': 'Non-empty date value'
                    },
                    # ... more issues
                ],
                'details': {
                    'validation_config': {...}
                }
            }
        """
        pass

    def update_progress(self, validation_job, progress: int):
        """
        Update job progress.

        Args:
            validation_job: ValidationJob instance
            progress: int between 0 and 100
        """
        validation_job.update_progress(progress)
        logger.debug(f"Validation progress: {progress}%")

    def get_total_rows(self) -> int:
        """
        Get total number of rows in data table.

        Returns:
            int: Row count
        """
        try:
            result = self.conn.execute("SELECT COUNT(*) FROM data").fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get row count: {e}")
            return 0

    def get_column_names(self) -> List[str]:
        """
        Get list of column names in data table.

        Returns:
            List[str]: Column names
        """
        try:
            result = self.conn.execute("DESCRIBE data").fetchall()
            return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Failed to get column names: {e}")
            return []

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False  # Don't suppress exceptions
