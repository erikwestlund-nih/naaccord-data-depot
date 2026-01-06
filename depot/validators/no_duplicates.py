"""
No Duplicates Validator

Checks that all values in a column are unique (no duplicates).

Rule Key: no_duplicates

Parameters:
- severity: "warning" or "error" (optional, default: "error")

Example definition:
{
  "name": "cohortPatientId",
  "type": "id",
  "validators": [
    {
      "type": "no_duplicates",
      "severity": "error"
    }
  ]
}

Returns:
- passed: False if duplicates found
- affected_row_count: Number of duplicate values
- row_numbers: Row numbers with duplicates (up to 1000)
- meta: duplicate_values with counts (PHI-safe)
"""

from typing import Dict, Any
from .base import BaseValidator, ValidationResult
import logging

logger = logging.getLogger(__name__)


class NoDuplicatesValidator(BaseValidator):
    """
    Validator that checks for duplicate values in a column.

    For PHI-sensitive columns (like cohortPatientId), only reports:
    - Row numbers where duplicates occur
    - Count of duplicates per value
    - Does NOT show the actual duplicate patient IDs
    """

    rule_key = "no_duplicates"
    default_severity = "error"
    requires_params = []  # No required parameters

    def validate(
        self,
        conn,
        table_name: str,
        column_name: str,
        params: Dict[str, Any]
    ) -> ValidationResult:
        """
        Check for duplicate values in column.

        Args:
            conn: DuckDB connection
            table_name: Name of table to validate
            column_name: Name of column to check
            params: Validator parameters (severity optional)

        Returns:
            ValidationResult with duplicate detection results
        """
        try:
            # Find duplicate values and their counts
            duplicate_query = f"""
                SELECT "{column_name}", COUNT(*) as dup_count
                FROM {table_name}
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" != ''
                GROUP BY "{column_name}"
                HAVING COUNT(*) > 1
                ORDER BY dup_count DESC
                LIMIT 100
            """

            duplicates = conn.execute(duplicate_query).fetchall()

            # If no duplicates found, validation passed
            if not duplicates:
                return ValidationResult(
                    passed=True,
                    rule_key=self.rule_key,
                    rule_params=params,
                    severity=params.get('severity', self.default_severity),
                    message=f"No duplicate values found in {column_name}",
                    affected_row_count=0,
                    meta={'duplicate_value_count': 0}
                )

            # Count total rows with duplicates
            total_affected = sum(count for _, count in duplicates)

            # Get row numbers for duplicates (PHI-safe - just row numbers)
            # We get row numbers for the first duplicate value only
            first_duplicate_value = duplicates[0][0]

            row_numbers_query = f"""
                SELECT row_number() OVER () as row_num
                FROM {table_name}
                WHERE "{column_name}" = ?
                LIMIT 1000
            """

            row_result = conn.execute(row_numbers_query, [first_duplicate_value]).fetchall()
            row_numbers = [row[0] for row in row_result]

            # Build duplicate summary (PHI-safe - show counts only)
            duplicate_summary = []
            for value, count in duplicates[:10]:  # Show top 10
                # For PHI-sensitive columns, don't show the actual value
                # Instead show: "Value appears N times"
                duplicate_summary.append({
                    'count': count,
                    'description': f"Value appears {count} times"
                })

            # Build message
            duplicate_count = len(duplicates)
            message = (
                f"Found {duplicate_count} duplicate value(s) "
                f"affecting {total_affected} rows in {column_name}"
            )

            return ValidationResult(
                passed=False,
                rule_key=self.rule_key,
                rule_params=params,
                severity=params.get('severity', self.default_severity),
                message=message,
                affected_row_count=total_affected,
                row_numbers=row_numbers,
                invalid_value=None,  # Don't show value for PHI columns
                meta={
                    'duplicate_value_count': duplicate_count,
                    'duplicate_summary': duplicate_summary,
                    'top_duplicate_count': duplicates[0][1] if duplicates else 0
                }
            )

        except Exception as e:
            logger.error(f"NoDuplicatesValidator failed on {column_name}: {e}")
            return ValidationResult(
                passed=False,
                rule_key=self.rule_key,
                rule_params=params,
                severity="error",
                message=f"Duplicate check failed: {str(e)}",
                meta={'error': str(e)}
            )
