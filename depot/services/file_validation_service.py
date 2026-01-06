"""
File Validation Service

Pre-upload validation service that checks CSV files for:
- Encoding detection
- BOM markers
- Line ending issues
- CSV structure validation
- Column count consistency
- Dangerous special characters

This validation happens BEFORE files are stored to catch issues early.
"""

import csv
import io
import logging
import re
from typing import Dict, List, Tuple, Any
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.utils import timezone

logger = logging.getLogger(__name__)


class FileValidationService:
    """Service for validating uploaded CSV files before processing."""

    # UTF-8 BOM bytes
    UTF8_BOM = b'\xef\xbb\xbf'

    # Dangerous characters that could break CSV parsing
    DANGEROUS_CHARS = [
        '\x00',  # Null byte
        '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',  # Control chars
        '\x08', '\x0b', '\x0c', '\x0e', '\x0f',  # More control chars
        '\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17',
        '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e', '\x1f'
    ]

    @classmethod
    def validate_file(cls, uploaded_file: DjangoUploadedFile) -> Dict[str, Any]:
        """
        Perform comprehensive pre-upload validation on a CSV file.

        Args:
            uploaded_file: Django uploaded file object

        Returns:
            Dictionary with validation results:
                - valid: bool - Whether file passed validation
                - errors: list - List of validation error messages
                - warnings: list - List of non-fatal warnings
                - metadata: dict - File metadata (encoding, BOM, etc.)
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'metadata': {
                'detected_encoding': 'utf-8',  # Default assumption
                'has_bom': False,
                'has_crlf': False,
                'line_count': 0,
                'header_column_count': 0,
                'validation_performed_at': timezone.now()
            }
        }

        try:
            # Reset file position
            uploaded_file.seek(0)

            # Read first chunk to detect encoding and BOM
            first_chunk = uploaded_file.read(1024 * 1024)  # 1MB sample
            uploaded_file.seek(0)

            # Detect BOM
            if first_chunk.startswith(cls.UTF8_BOM):
                results['metadata']['has_bom'] = True
                results['warnings'].append('File has UTF-8 BOM marker (will be removed during processing)')
                # Remove BOM for further analysis
                first_chunk = first_chunk[len(cls.UTF8_BOM):]

            # Detect line endings
            if b'\r\n' in first_chunk:
                results['metadata']['has_crlf'] = True
                results['warnings'].append('File has Windows line endings (CRLF will be converted to LF)')

            # Detect encoding
            encoding = cls._detect_encoding(first_chunk)
            results['metadata']['detected_encoding'] = encoding

            # Read entire file for validation
            uploaded_file.seek(0)
            raw_content = uploaded_file.read()

            # Remove BOM if present for parsing
            if raw_content.startswith(cls.UTF8_BOM):
                raw_content = raw_content[len(cls.UTF8_BOM):]

            # Try to decode with detected encoding
            try:
                text_content = raw_content.decode(encoding)
            except UnicodeDecodeError as e:
                results['valid'] = False
                results['errors'].append(f'File encoding error: Cannot decode as {encoding}. Error: {str(e)}')
                return results

            # Check for dangerous characters
            dangerous_found = cls._check_dangerous_characters(text_content)
            if dangerous_found:
                results['valid'] = False
                results['errors'].append(
                    f'File contains dangerous control characters: {", ".join(dangerous_found)}. '
                    f'These characters can break CSV parsing and must be removed.'
                )

            # Validate CSV structure
            csv_validation = cls._validate_csv_structure(text_content, uploaded_file.name)

            # Merge CSV validation results
            results['metadata']['line_count'] = csv_validation['line_count']
            results['metadata']['header_column_count'] = csv_validation['header_column_count']

            if not csv_validation['valid']:
                results['valid'] = False
                results['errors'].extend(csv_validation['errors'])

            results['warnings'].extend(csv_validation.get('warnings', []))

            # Reset file position for subsequent processing
            uploaded_file.seek(0)

        except Exception as e:
            logger.exception(f'Unexpected error during file validation: {str(e)}')
            results['valid'] = False
            results['errors'].append(f'Validation error: {str(e)}')

        return results

    @classmethod
    def _detect_encoding(cls, sample: bytes) -> str:
        """
        Detect file encoding from a sample.

        Args:
            sample: Byte sample from file

        Returns:
            Detected encoding string (defaults to 'utf-8')
        """
        # Try to import chardet for better encoding detection
        try:
            import chardet
            result = chardet.detect(sample)
            detected = result.get('encoding', 'utf-8')
            confidence = result.get('confidence', 0)

            # If low confidence, fall back to utf-8
            if confidence < 0.7:
                logger.warning(f'Low confidence ({confidence}) for detected encoding {detected}, using utf-8')
                return 'utf-8'

            # Normalize encoding names
            if detected.lower() in ['ascii', 'us-ascii']:
                return 'utf-8'  # ASCII is subset of UTF-8

            return detected
        except ImportError:
            # chardet not available, try simple detection
            logger.warning('chardet not available, using simple encoding detection')

            # Try UTF-8 first
            try:
                sample.decode('utf-8')
                return 'utf-8'
            except UnicodeDecodeError:
                pass

            # Try latin-1 (works for most Western European text)
            try:
                sample.decode('latin-1')
                return 'latin-1'
            except UnicodeDecodeError:
                pass

            # Default to utf-8
            return 'utf-8'

    @classmethod
    def _check_dangerous_characters(cls, text_content: str) -> List[str]:
        """
        Check for dangerous control characters in text.

        Args:
            text_content: Decoded text content

        Returns:
            List of dangerous characters found (as hex codes)
        """
        found = []
        for char in cls.DANGEROUS_CHARS:
            if char in text_content:
                hex_code = f'\\x{ord(char):02x}'
                found.append(hex_code)

        return found

    @classmethod
    def _validate_csv_structure(cls, text_content: str, filename: str) -> Dict[str, Any]:
        """
        Validate CSV structure including column count consistency.

        Args:
            text_content: Decoded file content
            filename: Original filename for error messages

        Returns:
            Dictionary with validation results
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'line_count': 0,
            'header_column_count': 0
        }

        try:
            # Detect CSV dialect
            try:
                sample = text_content[:10240]  # First 10KB
                dialect = csv.Sniffer().sniff(sample, delimiters=',\t')
            except csv.Error:
                # Default to comma delimiter
                dialect = csv.excel
                dialect.delimiter = ','

            # Parse CSV
            reader = csv.reader(io.StringIO(text_content), dialect=dialect)

            header = None
            expected_columns = None
            row_number = 0
            errors_found = []

            for row in reader:
                row_number += 1

                # First row is header
                if row_number == 1:
                    if not row or all(cell.strip() == '' for cell in row):
                        result['valid'] = False
                        result['errors'].append('Header row is empty')
                        return result

                    header = row
                    expected_columns = len(row)
                    result['header_column_count'] = expected_columns

                    # Check for duplicate column names
                    col_names = [col.strip() for col in row]
                    duplicates = [name for name in col_names if col_names.count(name) > 1 and name != '']
                    if duplicates:
                        result['warnings'].append(
                            f'Duplicate column names found: {", ".join(set(duplicates))}'
                        )

                    continue

                # Skip empty rows
                if not row or all(cell.strip() == '' for cell in row):
                    continue

                # Check column count
                if len(row) != expected_columns:
                    error_msg = (
                        f'Row {row_number} has {len(row)} columns, expected {expected_columns}. '
                        f'First few cells: {row[:3]}'
                    )
                    errors_found.append(error_msg)

                    # Stop after 10 errors to avoid overwhelming the user
                    if len(errors_found) >= 10:
                        errors_found.append(f'... and possibly more rows with incorrect column counts')
                        break

            result['line_count'] = row_number

            # If we found column count errors, mark as invalid
            if errors_found:
                result['valid'] = False
                result['errors'].append(
                    f'CSV structure validation failed: {len(errors_found)} row(s) have incorrect column counts'
                )
                result['errors'].extend(errors_found)

            # Warn if file is empty
            if row_number <= 1:
                result['valid'] = False
                result['errors'].append('File appears to be empty (no data rows)')

        except csv.Error as e:
            result['valid'] = False
            result['errors'].append(f'CSV parsing error: {str(e)}')
        except Exception as e:
            logger.exception(f'Error validating CSV structure: {str(e)}')
            result['valid'] = False
            result['errors'].append(f'Unexpected error parsing CSV: {str(e)}')

        return result
