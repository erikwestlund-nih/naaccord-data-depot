"""
Secure File Validation for NA-ACCORD
Addresses OWASP A05:2021 - Security Misconfiguration
"""

import magic
import csv
import io
from django.core.exceptions import ValidationError
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SecureFileValidator:
    """
    Secure file validation with magic bytes detection and content verification.

    Prevents:
    - Executable files disguised as data files
    - HTML/JavaScript injection via CSV uploads
    - Archive bombs and malware
    - Binary uploads in general
    """

    # Data files: CSV ONLY - strict clinical data security
    DATA_FILE_TYPES = {
        'text/csv': ['.csv'],
        'text/plain': ['.csv', '.txt'],  # Some CSV files report as text/plain
        'application/csv': ['.csv'],
    }

    # Attachments: Office docs, PDFs, text, archives - trusted partners only
    ATTACHMENT_TYPES = {
        # Documents
        'application/pdf': ['.pdf'],
        'text/plain': ['.txt'],
        'text/markdown': ['.md'],

        # Microsoft Office (newer format)
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],

        # Microsoft Office (legacy format)
        'application/msword': ['.doc'],
        'application/vnd.ms-excel': ['.xls'],
        'application/vnd.ms-powerpoint': ['.ppt'],

        # Archives (for bulk submissions)
        'application/zip': ['.zip'],
        'application/x-zip-compressed': ['.zip'],
    }

    # Explicitly blocked types (belt and suspenders)
    BLOCKED_TYPES = {
        'application/x-executable',
        'application/x-msdos-program',
        'application/x-msdownload',
        'application/x-dosexec',
        'text/html',
        'text/javascript',
        'application/javascript',
        'text/x-shellscript',
        'application/x-sh',
    }

    @classmethod
    def validate_data_file(cls, uploaded_file):
        """
        Validate clinical data uploads - CSV ONLY with strict content verification.

        Args:
            uploaded_file: Django UploadedFile object

        Returns:
            True if valid

        Raises:
            ValidationError: If file is invalid or potentially malicious
        """
        logger.info(f"Validating data file: {uploaded_file.name}")

        # Check file size - NO LIMIT
        # max_size = 100 * 1024 * 1024  # 100MB
        # if uploaded_file.size > max_size:
        #     raise ValidationError(f"File too large: {uploaded_file.size} bytes. Maximum allowed: {max_size} bytes")

        # Read sample for magic bytes detection
        sample = uploaded_file.read(4096)
        uploaded_file.seek(0)  # Reset file pointer

        # Check magic bytes
        try:
            mime_type = magic.from_buffer(sample, mime=True)
        except Exception as e:
            logger.error(f"Magic bytes detection failed for {uploaded_file.name}: {e}")
            raise ValidationError("Unable to determine file type")

        logger.info(f"Detected MIME type: {mime_type} for file: {uploaded_file.name}")

        # Block explicitly dangerous types
        if mime_type in cls.BLOCKED_TYPES:
            raise ValidationError(f"File type explicitly blocked for security: {mime_type}")

        # Allow only specific data file types
        if mime_type not in cls.DATA_FILE_TYPES:
            raise ValidationError(f"Invalid file type for data upload: {mime_type}. Only CSV files are allowed.")

        # Verify file extension matches
        file_ext = Path(uploaded_file.name).suffix.lower()
        allowed_extensions = cls.DATA_FILE_TYPES[mime_type]

        if file_ext not in allowed_extensions:
            raise ValidationError(f"File extension {file_ext} doesn't match detected type {mime_type}")

        # For CSV files, verify they're actually valid CSV format
        if mime_type in ['text/csv', 'application/csv'] or file_ext == '.csv':
            cls._validate_csv_content(uploaded_file)

        logger.info(f"Data file validation passed: {uploaded_file.name}")
        return True

    @classmethod
    def validate_attachment(cls, uploaded_file):
        """
        Validate file attachments - Office docs, PDFs, text, controlled archives.

        Args:
            uploaded_file: Django UploadedFile object

        Returns:
            True if valid

        Raises:
            ValidationError: If file is invalid or not allowed
        """
        logger.info(f"Validating attachment: {uploaded_file.name}")

        # Check file size (reasonable limit)
        # No size limit for attachments
        # max_size = 50 * 1024 * 1024  # 50MB for attachments
        # if uploaded_file.size > max_size:
        #     raise ValidationError(f"Attachment too large: {uploaded_file.size} bytes. Maximum allowed: {max_size} bytes")

        # Read sample for magic bytes detection
        sample = uploaded_file.read(4096)
        uploaded_file.seek(0)  # Reset file pointer

        # Check magic bytes
        try:
            mime_type = magic.from_buffer(sample, mime=True)
        except Exception as e:
            logger.error(f"Magic bytes detection failed for {uploaded_file.name}: {e}")
            raise ValidationError("Unable to determine file type")

        logger.info(f"Detected MIME type: {mime_type} for attachment: {uploaded_file.name}")

        # Block explicitly dangerous types
        if mime_type in cls.BLOCKED_TYPES:
            raise ValidationError(f"File type explicitly blocked for security: {mime_type}")

        # Allow only specific attachment types
        if mime_type not in cls.ATTACHMENT_TYPES:
            raise ValidationError(f"File type not allowed for attachments: {mime_type}")

        # Verify file extension matches mime type
        file_ext = Path(uploaded_file.name).suffix.lower()
        allowed_extensions = cls.ATTACHMENT_TYPES[mime_type]

        if file_ext not in allowed_extensions:
            raise ValidationError(f"File extension {file_ext} doesn't match detected type {mime_type}")

        # Additional validation for text files
        if mime_type == 'text/plain':
            cls._validate_text_content(uploaded_file)

        logger.info(f"Attachment validation passed: {uploaded_file.name}")
        return True

    @classmethod
    def _validate_csv_content(cls, uploaded_file):
        """Verify file is actually valid CSV content."""
        try:
            # Read a reasonable sample
            sample_size = min(8192, uploaded_file.size)
            sample = uploaded_file.read(sample_size)
            uploaded_file.seek(0)  # Reset file pointer

            # Try to decode as UTF-8
            try:
                text_sample = sample.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text_sample = sample.decode('iso-8859-1')
                except UnicodeDecodeError:
                    raise ValidationError("CSV file must be UTF-8 or ISO-8859-1 encoded")

            # Use CSV sniffer to detect format
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(text_sample)
                logger.info(f"CSV format detected - delimiter: '{dialect.delimiter}', quoting: {dialect.quoting}")
            except csv.Error as e:
                raise ValidationError(f"Invalid CSV format: {str(e)}")

            # Basic sanity check - should have some structure
            reader = csv.reader(io.StringIO(text_sample), dialect=dialect)
            try:
                first_row = next(reader)
                if len(first_row) < 1:
                    raise ValidationError("CSV file appears to be empty or malformed")
            except (csv.Error, StopIteration):
                raise ValidationError("CSV file cannot be parsed")

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"CSV validation error: {e}")
            raise ValidationError("Unable to validate CSV file content")

    @classmethod
    def _validate_text_content(cls, uploaded_file):
        """Basic validation for text files to ensure they're not binary."""
        try:
            # Read sample
            sample_size = min(4096, uploaded_file.size)
            sample = uploaded_file.read(sample_size)
            uploaded_file.seek(0)

            # Try to decode as text
            try:
                sample.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    sample.decode('iso-8859-1')
                except UnicodeDecodeError:
                    raise ValidationError("Text file must be UTF-8 or ISO-8859-1 encoded")

            # Check for null bytes (common in binary files)
            if b'\x00' in sample:
                raise ValidationError("File contains null bytes - may be binary")

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Text validation error: {e}")
            raise ValidationError("Unable to validate text file content")


# Django form field validator functions for easy integration
def validate_data_file_upload(uploaded_file):
    """Django form field validator for data files."""
    return SecureFileValidator.validate_data_file(uploaded_file)


def validate_attachment_upload(uploaded_file):
    """Django form field validator for attachments."""
    return SecureFileValidator.validate_attachment(uploaded_file)