"""
File Cleaner Service

Handles cleaning of uploaded CSV files to remove Windows line endings,
BOM markers, and other encoding issues that can break DuckDB parsing.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileCleanerService:
    """
    Service for cleaning uploaded CSV files before processing.

    Fixes common issues:
    - UTF-8 BOM (Byte Order Mark) at file start
    - Windows line endings (CRLF -> LF)
    - Mixed line endings
    - Encoding issues
    """

    # UTF-8 BOM bytes
    UTF8_BOM = b'\xef\xbb\xbf'

    @classmethod
    def clean_file(cls, input_path: str, output_path: str = None) -> dict:
        """
        Clean a CSV file by removing BOM and converting line endings.

        Args:
            input_path: Path to input file
            output_path: Path to output file (if None, modifies in place)

        Returns:
            dict with cleaning results:
                - had_bom: bool
                - had_crlf: bool
                - lines_processed: int
                - bytes_before: int
                - bytes_after: int
        """
        input_path = Path(input_path)

        if output_path is None:
            output_path = input_path
        else:
            output_path = Path(output_path)

        # Read raw bytes
        with open(input_path, 'rb') as f:
            raw_content = f.read()

        original_size = len(raw_content)
        had_bom = False
        had_crlf = False

        # Remove BOM if present
        if raw_content.startswith(cls.UTF8_BOM):
            logger.info(f"Removing UTF-8 BOM from {input_path}")
            raw_content = raw_content[len(cls.UTF8_BOM):]
            had_bom = True

        # Convert CRLF to LF
        if b'\r\n' in raw_content:
            logger.info(f"Converting CRLF to LF in {input_path}")
            raw_content = raw_content.replace(b'\r\n', b'\n')
            had_crlf = True

        # Remove any remaining CR characters
        if b'\r' in raw_content:
            logger.info(f"Removing remaining CR characters from {input_path}")
            raw_content = raw_content.replace(b'\r', b'\n')

        # Count lines
        lines_processed = raw_content.count(b'\n')

        # Write cleaned content
        with open(output_path, 'wb') as f:
            f.write(raw_content)

        result = {
            'had_bom': had_bom,
            'had_crlf': had_crlf,
            'lines_processed': lines_processed,
            'bytes_before': original_size,
            'bytes_after': len(raw_content)
        }

        if had_bom or had_crlf:
            logger.info(f"File cleaned: {input_path} -> {output_path} (BOM: {had_bom}, CRLF: {had_crlf})")

        return result

    @classmethod
    def needs_cleaning(cls, file_path: str) -> dict:
        """
        Check if a file needs cleaning without modifying it.

        Args:
            file_path: Path to check

        Returns:
            dict with:
                - has_bom: bool
                - has_crlf: bool
                - needs_cleaning: bool
        """
        with open(file_path, 'rb') as f:
            # Read first 1MB to check
            sample = f.read(1024 * 1024)

        has_bom = sample.startswith(cls.UTF8_BOM)
        has_crlf = b'\r\n' in sample or b'\r' in sample

        return {
            'has_bom': has_bom,
            'has_crlf': has_crlf,
            'needs_cleaning': has_bom or has_crlf
        }
