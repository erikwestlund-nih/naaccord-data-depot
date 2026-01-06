"""
DuckDB Conversion Service

Converts CSV files to DuckDB format for efficient validation queries.

Architecture:
- Creates in-memory or file-based DuckDB database
- Loads CSV with automatic type detection
- Provides connection context for validators
- Handles cleanup of temporary database files

Usage:
    service = DuckDBConversionService(csv_path="/path/to/data.csv")
    db_path = service.create_database()

    # Use with context manager
    with service.get_connection() as conn:
        result = conn.execute("SELECT COUNT(*) FROM data").fetchone()

    service.cleanup()
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional
import duckdb
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DuckDBConversionException(Exception):
    """Raised when DuckDB conversion fails."""
    pass


class DuckDBConversionService:
    """
    Service for converting CSV files to DuckDB format.

    Creates temporary DuckDB database from CSV data for efficient
    querying during validation.
    """

    def __init__(self, csv_path: str, table_name: str = "data", in_memory: bool = False):
        """
        Initialize DuckDB conversion service.

        Args:
            csv_path: Path to CSV file to convert
            table_name: Name for the table in DuckDB (default: "data")
            in_memory: Use in-memory database instead of file (default: False)
        """
        self.csv_path = Path(csv_path)
        self.table_name = table_name
        self.in_memory = in_memory

        self.db_path: Optional[Path] = None
        self.temp_dir: Optional[Path] = None
        self.conn: Optional[duckdb.DuckDBPyConnection] = None

        if not self.csv_path.exists():
            raise DuckDBConversionException(f"CSV file not found: {self.csv_path}")

    def create_database(self) -> str:
        """
        Create DuckDB database from CSV file.

        Returns:
            Path to created database file (or ":memory:" for in-memory)

        Raises:
            DuckDBConversionException: If database creation fails
        """
        try:
            if self.in_memory:
                self.db_path = Path(":memory:")
                logger.info("Creating in-memory DuckDB database")
            else:
                # Create temporary directory for database
                self.temp_dir = Path(tempfile.mkdtemp(prefix="duckdb_"))
                self.db_path = self.temp_dir / "validation.duckdb"
                logger.info(f"Creating DuckDB database at {self.db_path}")

            # Connect to database
            self.conn = duckdb.connect(str(self.db_path))

            # Load CSV with automatic type detection
            # DuckDB's read_csv_auto handles:
            # - Header detection
            # - Type inference
            # - NULL value handling
            # - Quote handling
            self.conn.execute(f"""
                CREATE TABLE {self.table_name} AS
                SELECT * FROM read_csv_auto(
                    '{self.csv_path}',
                    header=true,
                    normalize_names=false,
                    all_varchar=false,
                    sample_size=100000,
                    ignore_errors=false
                )
            """)

            # Get row count for verification
            row_count = self.conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

            # Get column info
            columns = self.conn.execute(
                f"DESCRIBE {self.table_name}"
            ).fetchall()

            logger.info(
                f"Created DuckDB table '{self.table_name}' with {row_count} rows "
                f"and {len(columns)} columns"
            )

            # Log column types for debugging
            for col_name, col_type, *_ in columns:
                logger.debug(f"  {col_name}: {col_type}")

            return str(self.db_path)

        except Exception as e:
            logger.error(f"Failed to create DuckDB database: {e}")
            self.cleanup()
            raise DuckDBConversionException(f"Database creation failed: {e}")

    @contextmanager
    def get_connection(self):
        """
        Get connection to DuckDB database as context manager.

        Usage:
            with service.get_connection() as conn:
                result = conn.execute("SELECT * FROM data LIMIT 10")

        Yields:
            DuckDB connection object

        Raises:
            DuckDBConversionException: If database not created yet
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        try:
            yield self.conn
        except Exception as e:
            logger.error(f"Error during database operation: {e}")
            raise

    def execute_query(self, query: str) -> list:
        """
        Execute a SQL query and return results.

        Args:
            query: SQL query to execute

        Returns:
            List of result rows

        Raises:
            DuckDBConversionException: If query execution fails
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        try:
            result = self.conn.execute(query).fetchall()
            return result
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise DuckDBConversionException(f"Query failed: {e}")

    def get_column_names(self) -> list:
        """
        Get list of column names from the table.

        Returns:
            List of column names

        Raises:
            DuckDBConversionException: If database not created yet
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        try:
            result = self.conn.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{self.table_name}' "
                f"ORDER BY ordinal_position"
            ).fetchall()

            return [row[0] for row in result]

        except Exception as e:
            logger.error(f"Failed to get column names: {e}")
            raise DuckDBConversionException(f"Column lookup failed: {e}")

    def get_column_types(self) -> dict:
        """
        Get dictionary of column names to types.

        Returns:
            Dict mapping column names to DuckDB type strings

        Raises:
            DuckDBConversionException: If database not created yet
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        try:
            result = self.conn.execute(f"DESCRIBE {self.table_name}").fetchall()
            return {row[0]: row[1] for row in result}

        except Exception as e:
            logger.error(f"Failed to get column types: {e}")
            raise DuckDBConversionException(f"Type lookup failed: {e}")

    def get_row_count(self) -> int:
        """
        Get total number of rows in the table.

        Returns:
            Row count

        Raises:
            DuckDBConversionException: If database not created yet
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        try:
            result = self.conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()
            return result[0]

        except Exception as e:
            logger.error(f"Failed to get row count: {e}")
            raise DuckDBConversionException(f"Row count failed: {e}")

    def get_database_info(self) -> dict:
        """
        Get information about the created database.

        Returns:
            Dict with database metadata

        Raises:
            DuckDBConversionException: If database not created yet
        """
        if self.conn is None:
            raise DuckDBConversionException(
                "Database not created. Call create_database() first."
            )

        return {
            'csv_path': str(self.csv_path),
            'db_path': str(self.db_path),
            'table_name': self.table_name,
            'in_memory': self.in_memory,
            'row_count': self.get_row_count(),
            'columns': self.get_column_names(),
            'column_types': self.get_column_types()
        }

    def cleanup(self):
        """
        Clean up database connection and temporary files.

        Closes connection and removes temporary database files.
        Safe to call multiple times.
        """
        # Close connection
        if self.conn is not None:
            try:
                self.conn.close()
                logger.debug("Closed DuckDB connection")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self.conn = None

        # Remove temporary directory
        if self.temp_dir is not None and self.temp_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
                logger.info(f"Removed temporary directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Error removing temp directory: {e}")
            finally:
                self.temp_dir = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        return False

    def __del__(self):
        """Ensure cleanup on deletion."""
        self.cleanup()
