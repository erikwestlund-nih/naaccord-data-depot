"""
Service for combining multiple DuckDB files into a single validation dataset.

When a table has multiple uploaded files, we need to combine them for validation
so that we can validate the complete dataset and catch cross-file issues.
"""
import duckdb
import logging
from pathlib import Path
from typing import List, Optional
from django.utils import timezone

from depot.models import DataTableFile, PHIFileTracking
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class DuckDBCombinerService:
    """Combines multiple DuckDB files for unified validation."""

    def __init__(self, workspace_dir: Path):
        """
        Initialize combiner service.

        Args:
            workspace_dir: Directory for temporary workspace files
        """
        self.workspace_dir = workspace_dir
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def combine_files(self, data_files: List[DataTableFile], cohort, user) -> Optional[str]:
        """
        Combine multiple DuckDB files into one for validation.

        Adds metadata columns:
        - __source_file_id: Which DataTableFile the row came from
        - __source_row_number: Row number in the original file

        Args:
            data_files: List of DataTableFile objects with DuckDB files
            cohort: Cohort for PHI tracking
            user: User for PHI tracking

        Returns:
            Path to combined DuckDB file, or None if only one file
        """
        # Filter to files that have DuckDB
        files_with_duckdb = [f for f in data_files if f.duckdb_file_path]

        if len(files_with_duckdb) == 0:
            logger.warning("No DuckDB files to combine")
            return None

        if len(files_with_duckdb) == 1:
            logger.info("Only one DuckDB file, no need to combine")
            return files_with_duckdb[0].duckdb_file_path

        logger.info(f"Combining {len(files_with_duckdb)} DuckDB files for validation")

        # Create combined DuckDB file
        combined_filename = f"combined_{data_files[0].data_table.id}_{int(timezone.now().timestamp() * 1000)}.duckdb"
        combined_path = self.workspace_dir / combined_filename

        try:
            conn = duckdb.connect(str(combined_path))

            # Build UNION ALL query
            union_queries = []

            for data_file in files_with_duckdb:
                # Attach the source DuckDB
                source_db_path = data_file.duckdb_file_path

                # Read from the source DuckDB and add metadata columns
                # Use row_number() window function to track row numbers
                query = f"""
                    SELECT
                        *,
                        {data_file.id} AS __source_file_id,
                        row_number() OVER () AS __source_row_number
                    FROM read_parquet('{source_db_path}')
                """
                union_queries.append(query)

            # Combine all queries with UNION ALL
            combined_query = " UNION ALL ".join(union_queries)

            # Create the combined table
            conn.execute(f"CREATE TABLE data AS {combined_query}")

            # Get row count for verification
            row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
            logger.info(f"Combined DuckDB contains {row_count} total rows from {len(files_with_duckdb)} files")

            conn.close()

            # Log PHI tracking
            PHIFileTracking.log_operation(
                cohort=cohort,
                user=user,
                action='work_copy_created',
                file_path=str(combined_path),
                file_type='combined_duckdb',
                file_size=combined_path.stat().st_size,
                metadata={
                    'source_files': [f.id for f in files_with_duckdb],
                    'row_count': row_count,
                    'purpose_subdirectory': 'validation',
                    'expected_cleanup_by': (timezone.now() + timezone.timedelta(hours=2)).isoformat()
                }
            )

            return str(combined_path)

        except Exception as e:
            logger.error(f"Failed to combine DuckDB files: {e}", exc_info=True)
            # Cleanup on failure
            if combined_path.exists():
                combined_path.unlink()
            raise
