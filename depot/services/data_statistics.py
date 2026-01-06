"""
Data File Statistics Service

Computes basic statistics for CSV columns using DuckDB.

Architecture:
- Uses DuckDB for efficient statistical queries
- Computes null counts, empty counts, distinct values
- Provides column-level summaries for ValidationVariable records

Usage:
    service = DataFileStatisticsService(duckdb_connection)
    stats = service.compute_column_statistics("cohortPatientId")
    # Returns: {total_rows, null_count, empty_count, distinct_count, ...}
"""

import logging
from typing import Dict, Optional
import duckdb

logger = logging.getLogger(__name__)


class StatisticsComputationException(Exception):
    """Raised when statistics computation fails."""
    pass


class DataFileStatisticsService:
    """
    Service for computing column-level statistics from DuckDB data.

    Provides methods to calculate basic statistics needed for
    ValidationVariable summary fields.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection, table_name: str = "data"):
        """
        Initialize statistics service with DuckDB connection.

        Args:
            connection: Active DuckDB connection
            table_name: Name of table to query (default: "data")
        """
        self.conn = connection
        self.table_name = table_name

    def compute_column_statistics(self, column_name: str) -> Dict:
        """
        Compute comprehensive statistics for a single column.

        Args:
            column_name: Name of column to analyze

        Returns:
            Dict containing:
                - total_rows: Total number of rows
                - null_count: Number of NULL values
                - empty_count: Number of empty strings (if string column)
                - distinct_count: Number of distinct non-null values
                - sample_values: List of sample values (up to 10)

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            # Get total row count
            total_rows = self.conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

            # Get null count
            null_count = self.conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {self.table_name}
                WHERE "{column_name}" IS NULL
                """
            ).fetchone()[0]

            # Get empty string count (for string columns)
            empty_count = 0
            try:
                empty_count = self.conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {self.table_name}
                    WHERE "{column_name}" = ''
                    """
                ).fetchone()[0]
            except:
                # Column might not be string type, skip empty check
                pass

            # Get distinct count (excluding nulls and empty strings)
            distinct_count = self.conn.execute(
                f"""
                SELECT COUNT(DISTINCT "{column_name}")
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" != ''
                """
            ).fetchone()[0]

            # Get sample values
            sample_values = self.conn.execute(
                f"""
                SELECT DISTINCT "{column_name}"
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" != ''
                LIMIT 10
                """
            ).fetchall()

            sample_values = [str(row[0]) for row in sample_values]

            logger.debug(
                f"Statistics for {column_name}: "
                f"{total_rows} total, {null_count} null, "
                f"{empty_count} empty, {distinct_count} distinct"
            )

            return {
                'total_rows': total_rows,
                'null_count': null_count,
                'empty_count': empty_count,
                'distinct_count': distinct_count,
                'sample_values': sample_values,
                'valid_count': total_rows - null_count - empty_count,
                'invalid_count': 0  # Updated by validators
            }

        except Exception as e:
            logger.error(f"Failed to compute statistics for {column_name}: {e}")
            raise StatisticsComputationException(
                f"Statistics computation failed for {column_name}: {e}"
            )

    def compute_all_columns_statistics(self) -> Dict[str, Dict]:
        """
        Compute statistics for all columns in the table.

        Returns:
            Dict mapping column names to their statistics

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            # Get all column names
            columns_result = self.conn.execute(
                f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{self.table_name}'
                ORDER BY ordinal_position
                """
            ).fetchall()

            column_names = [row[0] for row in columns_result]

            # Compute statistics for each column
            all_stats = {}
            for col_name in column_names:
                try:
                    all_stats[col_name] = self.compute_column_statistics(col_name)
                except Exception as e:
                    logger.warning(f"Skipping statistics for {col_name}: {e}")
                    all_stats[col_name] = {
                        'error': str(e),
                        'total_rows': 0,
                        'null_count': 0,
                        'empty_count': 0,
                        'distinct_count': 0,
                        'sample_values': [],
                        'valid_count': 0,
                        'invalid_count': 0
                    }

            logger.info(f"Computed statistics for {len(all_stats)} columns")
            return all_stats

        except Exception as e:
            logger.error(f"Failed to compute all statistics: {e}")
            raise StatisticsComputationException(
                f"Batch statistics computation failed: {e}"
            )

    def get_value_distribution(self, column_name: str, limit: int = 20) -> Dict:
        """
        Get value distribution (frequency counts) for a column.

        Args:
            column_name: Name of column to analyze
            limit: Maximum number of distinct values to return

        Returns:
            Dict containing:
                - distributions: List of (value, count) tuples
                - total_distinct: Total number of distinct values
                - truncated: Whether results were truncated

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            # Get value counts
            result = self.conn.execute(
                f"""
                SELECT "{column_name}", COUNT(*) as count
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" != ''
                GROUP BY "{column_name}"
                ORDER BY count DESC
                LIMIT {limit}
                """
            ).fetchall()

            distributions = [(str(row[0]), row[1]) for row in result]

            # Get total distinct count
            total_distinct = self.conn.execute(
                f"""
                SELECT COUNT(DISTINCT "{column_name}")
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" != ''
                """
            ).fetchone()[0]

            return {
                'distributions': distributions,
                'total_distinct': total_distinct,
                'truncated': total_distinct > limit
            }

        except Exception as e:
            logger.error(f"Failed to get value distribution for {column_name}: {e}")
            raise StatisticsComputationException(
                f"Distribution computation failed for {column_name}: {e}"
            )

    def get_numeric_statistics(self, column_name: str) -> Optional[Dict]:
        """
        Get numeric statistics for a numeric column.

        Args:
            column_name: Name of column to analyze

        Returns:
            Dict with min, max, mean, median, std_dev, or None if not numeric

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            result = self.conn.execute(
                f"""
                SELECT
                    MIN("{column_name}") as min_val,
                    MAX("{column_name}") as max_val,
                    AVG("{column_name}") as mean_val,
                    MEDIAN("{column_name}") as median_val,
                    STDDEV("{column_name}") as std_dev
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                """
            ).fetchone()

            if result is None or result[0] is None:
                return None

            return {
                'min': float(result[0]) if result[0] is not None else None,
                'max': float(result[1]) if result[1] is not None else None,
                'mean': float(result[2]) if result[2] is not None else None,
                'median': float(result[3]) if result[3] is not None else None,
                'std_dev': float(result[4]) if result[4] is not None else None
            }

        except Exception as e:
            # Column likely not numeric, return None
            logger.debug(f"Column {column_name} is not numeric: {e}")
            return None

    def get_date_statistics(self, column_name: str) -> Optional[Dict]:
        """
        Get date range statistics for a date column.

        Args:
            column_name: Name of column to analyze

        Returns:
            Dict with min_date, max_date, or None if not date-like

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            result = self.conn.execute(
                f"""
                SELECT
                    MIN(TRY_CAST("{column_name}" AS DATE)) as min_date,
                    MAX(TRY_CAST("{column_name}" AS DATE)) as max_date
                FROM {self.table_name}
                WHERE "{column_name}" IS NOT NULL
                """
            ).fetchone()

            if result is None or result[0] is None:
                return None

            return {
                'min_date': str(result[0]) if result[0] is not None else None,
                'max_date': str(result[1]) if result[1] is not None else None
            }

        except Exception as e:
            logger.debug(f"Column {column_name} is not date-like: {e}")
            return None

    def get_table_summary(self) -> Dict:
        """
        Get overall table summary statistics.

        Returns:
            Dict with table-level metadata

        Raises:
            StatisticsComputationException: If computation fails
        """
        try:
            # Get row count
            row_count = self.conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

            # Get column count
            col_count = self.conn.execute(
                f"""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = '{self.table_name}'
                """
            ).fetchone()[0]

            # Get column names and types
            columns = self.conn.execute(
                f"DESCRIBE {self.table_name}"
            ).fetchall()

            column_info = [
                {'name': row[0], 'type': row[1]}
                for row in columns
            ]

            return {
                'row_count': row_count,
                'column_count': col_count,
                'columns': column_info
            }

        except Exception as e:
            logger.error(f"Failed to get table summary: {e}")
            raise StatisticsComputationException(
                f"Table summary failed: {e}"
            )
