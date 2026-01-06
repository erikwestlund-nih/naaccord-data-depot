"""
Large File Processing Utilities

Shared utilities for memory-efficient processing of large CSV files.
Used by both precheck validation and upload workflows.

Key optimizations:
- Stream file reading instead of loading entire file into memory
- DuckDB memory limits with disk spilling for large datasets
- File path passthrough to avoid Python memory overhead
"""

import os
import csv
import hashlib
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Default DuckDB memory limit (can be overridden)
DEFAULT_DUCKDB_MEMORY_LIMIT = '2GB'
DEFAULT_DUCKDB_TEMP_DIR = '/tmp/duckdb_temp'


def get_file_path_from_storage(storage, relative_path: str) -> str:
    """
    Get absolute file path from storage, avoiding loading content into memory.

    Args:
        storage: Storage instance (LocalFileSystemStorage or similar)
        relative_path: Relative path within storage

    Returns:
        Absolute filesystem path

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    absolute_path = storage.get_absolute_path(relative_path)

    if not os.path.exists(absolute_path):
        raise FileNotFoundError(f'File not found: {absolute_path}')

    return absolute_path


def stream_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Analyze file metadata by streaming - never loads entire file into memory.

    Args:
        file_path: Absolute path to file

    Returns:
        Dict with file_size, file_hash, line_count, encoding info
    """
    import codecs

    # Try to import chardet for encoding detection
    try:
        import chardet
    except ImportError:
        try:
            from charset_normalizer import from_bytes as chardet_detect
            class ChardetWrapper:
                @staticmethod
                def detect(byte_str):
                    results = chardet_detect(byte_str)
                    if results and len(results) > 0:
                        result = results.best()
                        if result:
                            return {'encoding': result.encoding or 'utf-8', 'confidence': 0.9}
                    return {'encoding': 'utf-8', 'confidence': 0.5}
            chardet = ChardetWrapper()
        except ImportError:
            class ChardetFallback:
                @staticmethod
                def detect(byte_str):
                    return {'encoding': 'utf-8', 'confidence': 1.0}
            chardet = ChardetFallback()

    hasher = hashlib.sha256()
    file_size = 0
    line_count = 0
    first_10kb = b''
    first_line_bytes = b''
    found_first_line = False

    CHUNK_SIZE = 65536  # 64KB chunks

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            hasher.update(chunk)
            file_size += len(chunk)
            line_count += chunk.count(b'\n')

            # Collect first 10KB for encoding detection
            if len(first_10kb) < 10000:
                first_10kb += chunk[:10000 - len(first_10kb)]

            # Extract first line for header
            if not found_first_line:
                newline_pos = chunk.find(b'\n')
                if newline_pos != -1:
                    first_line_bytes += chunk[:newline_pos]
                    found_first_line = True
                else:
                    first_line_bytes += chunk

    # Detect BOM and encoding
    has_bom = first_10kb.startswith(codecs.BOM_UTF8)
    encoding_result = chardet.detect(first_10kb)
    encoding = encoding_result.get('encoding') or 'utf-8'
    has_crlf = b'\r\n' in first_10kb

    # Extract header columns
    columns = []
    if first_line_bytes:
        try:
            if has_bom:
                header_text = first_line_bytes.decode('utf-8-sig')
            else:
                header_text = first_line_bytes.decode(encoding, errors='replace')
            columns = [col.strip() for col in header_text.split(',')]
        except Exception as e:
            logger.warning(f'Failed to decode header line: {e}')

    return {
        'file_size': file_size,
        'file_hash': hasher.hexdigest(),
        'line_count': line_count,
        'encoding': encoding,
        'has_bom': has_bom,
        'has_crlf': has_crlf,
        'columns': columns,
        'header_column_count': len(columns),
    }


def stream_csv_integrity_check(
    file_path: str,
    encoding: str = 'utf-8',
    has_bom: bool = False,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    Check CSV integrity by streaming - never loads entire file into memory.

    Args:
        file_path: Absolute path to CSV file
        encoding: File encoding
        has_bom: Whether file has BOM
        progress_callback: Optional callback(row_num, total_estimate) for progress updates

    Returns:
        Dict with total_rows, malformed_rows list, expected_columns
    """
    effective_encoding = 'utf-8-sig' if has_bom else encoding

    with open(file_path, 'r', encoding=effective_encoding, newline='') as f:
        csv_reader = csv.reader(f)

        # Read header
        try:
            header = next(csv_reader)
            expected_columns = len(header)
        except StopIteration:
            raise ValueError('File is empty or has no header row')

        malformed_rows = []
        total_rows = 1  # Header counts as row 1

        for row_num, row in enumerate(csv_reader, start=2):
            total_rows = row_num

            if len(row) != expected_columns:
                malformed_rows.append({
                    'row': row_num,
                    'expected_columns': expected_columns,
                    'actual_columns': len(row),
                })

            # Progress callback every 100K rows
            if progress_callback and row_num % 100000 == 0:
                progress_callback(row_num, None)

    return {
        'total_rows': total_rows,
        'malformed_rows': malformed_rows,
        'expected_columns': expected_columns,
        'header': header,
    }


def create_duckdb_from_csv(
    csv_path: str,
    duckdb_path: Optional[str] = None,
    memory_limit: str = DEFAULT_DUCKDB_MEMORY_LIMIT,
    temp_directory: str = DEFAULT_DUCKDB_TEMP_DIR,
) -> Tuple[str, int]:
    """
    Create DuckDB database from CSV file with memory limits.

    DuckDB reads directly from the CSV file - no Python memory overhead.
    Memory limit ensures large files spill to disk instead of OOM.

    Args:
        csv_path: Absolute path to CSV file
        duckdb_path: Optional path for DuckDB file (creates temp if None)
        memory_limit: DuckDB memory limit (e.g., '2GB')
        temp_directory: Directory for DuckDB temp files

    Returns:
        Tuple of (duckdb_path, row_count)
    """
    import duckdb

    # Create temp DuckDB file if not specified
    if duckdb_path is None:
        fd, duckdb_path = tempfile.mkstemp(suffix='.duckdb', prefix='data_')
        os.close(fd)
        os.unlink(duckdb_path)  # Remove empty file so DuckDB can create fresh
    elif os.path.exists(duckdb_path):
        os.unlink(duckdb_path)

    # Ensure temp directory exists
    os.makedirs(temp_directory, exist_ok=True)

    conn = duckdb.connect(duckdb_path)
    try:
        # Configure memory limits - DuckDB will spill to disk for large datasets
        conn.execute(f"SET memory_limit='{memory_limit}'")
        conn.execute(f"SET temp_directory='{temp_directory}'")

        logger.info(f'DuckDB configured: memory_limit={memory_limit}, temp_dir={temp_directory}')

        # Load CSV directly - DuckDB streams from file, no Python memory
        conn.execute("""
            CREATE TABLE data AS
            SELECT *, row_number() OVER () as row_no
            FROM read_csv_auto(?, header=true, ignore_errors=false)
        """, [csv_path])

        # Get row count
        row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]

        logger.info(f'DuckDB loaded {row_count:,} rows from {csv_path}')

        return duckdb_path, row_count

    finally:
        conn.close()


def create_duckdb_connection_with_limits(
    duckdb_path: str,
    memory_limit: str = DEFAULT_DUCKDB_MEMORY_LIMIT,
    temp_directory: str = DEFAULT_DUCKDB_TEMP_DIR,
):
    """
    Create DuckDB connection with memory limits configured.

    Args:
        duckdb_path: Path to DuckDB file
        memory_limit: DuckDB memory limit
        temp_directory: Directory for temp files

    Returns:
        DuckDB connection with memory limits set
    """
    import duckdb

    os.makedirs(temp_directory, exist_ok=True)

    conn = duckdb.connect(duckdb_path)
    conn.execute(f"SET memory_limit='{memory_limit}'")
    conn.execute(f"SET temp_directory='{temp_directory}'")

    return conn


def stream_process_csv(
    input_path: str,
    output_path: str,
    header_transform: Optional[callable] = None,
    row_transform: Optional[callable] = None,
    encoding: str = 'utf-8',
    has_bom: bool = False,
) -> Dict[str, Any]:
    """
    Stream-process a CSV file, transforming header and/or rows.

    Never loads entire file into memory - processes line by line.

    Args:
        input_path: Input CSV file path
        output_path: Output CSV file path
        header_transform: Optional function to transform header row
        row_transform: Optional function to transform data rows
        encoding: File encoding
        has_bom: Whether file has BOM

    Returns:
        Dict with rows_processed count
    """
    effective_encoding = 'utf-8-sig' if has_bom else encoding

    row_count = 0

    with open(input_path, 'r', encoding=effective_encoding, newline='') as infile, \
         open(output_path, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        # Process header
        header = next(reader)
        if header_transform:
            header = header_transform(header)
        writer.writerow(header)

        # Stream rows
        if row_transform:
            for row in reader:
                writer.writerow(row_transform(row))
                row_count += 1
        else:
            # Fast path - write lines directly without CSV parsing
            outfile.writelines(line for line in infile)
            # Count lines for reporting (approximate)
            infile.seek(0)
            row_count = sum(1 for _ in infile) - 1  # Subtract header

    return {'rows_processed': row_count}


def copy_file_streaming(source_path: str, dest_path: str, chunk_size: int = 65536) -> int:
    """
    Copy file by streaming - never loads entire file into memory.

    Args:
        source_path: Source file path
        dest_path: Destination file path
        chunk_size: Chunk size for streaming

    Returns:
        Number of bytes copied
    """
    bytes_copied = 0

    with open(source_path, 'rb') as src, open(dest_path, 'wb') as dst:
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            dst.write(chunk)
            bytes_copied += len(chunk)

    return bytes_copied
