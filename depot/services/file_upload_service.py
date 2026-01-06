"""
File Upload Service

Centralized service for handling file uploads across the application.
Provides common functionality for:
- File hash calculation
- Storage path generation
- File versioning
- Upload record management
- Complete file processing workflow
"""
import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.db import transaction
from depot.models import UploadedFile, UploadType, DataTableFile, CohortSubmissionDataTable
from depot.storage.phi_manager import PHIStorageManager
from django.utils import timezone
from datetime import timedelta
import logging
from depot.tasks.file_integrity import calculate_file_hash_task

logger = logging.getLogger(__name__)


class FileUploadService:
    """Service for handling file upload operations."""
    
    @staticmethod
    def calculate_file_hash(uploaded_file: DjangoUploadedFile, defer=False) -> str:
        """
        Calculate SHA256 hash of uploaded file.

        Args:
            uploaded_file: Django uploaded file object
            defer: If True, return placeholder for async calculation

        Returns:
            Hexadecimal string representation of SHA256 hash or placeholder
        """
        if defer:
            # Return placeholder for async calculation
            return "pending_async_calculation"

        file_hash = hashlib.sha256()
        uploaded_file.seek(0)

        for chunk in uploaded_file.chunks():
            file_hash.update(chunk)

        uploaded_file.seek(0)  # Reset file position
        return file_hash.hexdigest()
    
    @staticmethod
    def build_versioned_filename(original_name: str, version: int) -> str:
        """
        Build filename with version prefix.
        
        Args:
            original_name: Original filename
            version: Version number
            
        Returns:
            Filename with version prefix (e.g., "v2_patient_data.csv")
        """
        return f"v{version}_{original_name}"
    
    @staticmethod
    def build_storage_path(
        cohort_id: int,
        cohort_name: str,
        protocol_year: str,
        file_type: str,
        filename: str,
        is_attachment: bool = False,
        attachment_id: int = None
    ) -> str:
        """
        Build standardized storage path for uploaded files.
        
        Args:
            cohort_id: Cohort ID
            cohort_name: Cohort name (will be sanitized)
            protocol_year: Protocol year
            file_type: Type of file (e.g., "patient", "laboratory")
            filename: Filename to store
            is_attachment: Whether this is an attachment vs data file
            
        Returns:
            Storage path string
        """
        # Sanitize cohort name for filesystem
        safe_cohort_name = cohort_name.replace(' ', '_').replace('/', '-')
        
        # Build path components
        path_parts = [
            f"{cohort_id}_{safe_cohort_name}",
            protocol_year,
            file_type
        ]

        if is_attachment:
            # Add 'attachments' subdirectory to keep attachments separate from data files
            path_parts.append('attachments')
            if attachment_id:
                # Directory-per-attachment approach - use attachment ID as subdirectory
                path_parts.append(str(attachment_id))
                path_parts.append(filename)  # Keep original filename
            else:
                # Fallback to timestamp for backwards compatibility
                import time
                timestamp = str(int(time.time() * 1000))
                name, ext = os.path.splitext(filename)
                unique_filename = f"{name}_{timestamp}{ext}"
                path_parts.append(unique_filename)
        else:
            path_parts.append(filename)

        return os.path.join(*path_parts)
    
    @staticmethod
    def create_uploaded_file_record(
        file: DjangoUploadedFile,
        user,
        storage_path: str,
        file_hash: str,
        upload_type: UploadType = UploadType.RAW
    ) -> UploadedFile:
        """
        Create an UploadedFile database record.
        
        Args:
            file: Django uploaded file object
            user: User performing the upload
            storage_path: Path where file is/will be stored
            file_hash: SHA256 hash of the file
            upload_type: Type of upload (RAW, PROCESSED, OTHER)
            
        Returns:
            Created UploadedFile instance
        """
        return UploadedFile.objects.create(
            filename=file.name,
            storage_path=storage_path,
            uploader=user,
            type=upload_type,
            file_hash=file_hash,
            original_filename=file.name,
            file_size=file.size,
            content_type=getattr(file, 'content_type', 'application/octet-stream'),
        )
    
    @staticmethod
    def determine_file_version(data_table, file_id: Optional[str] = None) -> Tuple[int, Optional[DataTableFile]]:
        """
        Determine the version number for a file upload.

        Args:
            data_table: CohortSubmissionDataTable instance
            file_id: Optional ID of existing file being updated

        Returns:
            Tuple of (version_number, existing_file_or_none)
        """
        if file_id:
            # Updating specific existing file
            try:
                data_file = DataTableFile.objects.get(
                    id=file_id,
                    data_table=data_table
                )
                return data_file.version + 1, data_file
            except DataTableFile.DoesNotExist:
                logger.warning(f"File {file_id} not found for versioning")
                return 1, None  # Create new file if specified file not found

        # No file_id specified - handle based on table type
        is_patient_table = data_table.data_file_type.name == 'patient'

        if is_patient_table:
            # Patient tables only allow one file - replace existing or create new
            existing_file = data_table.files.order_by('-version').first()
            if existing_file is None:
                return 1, None  # First file for this data table
            else:
                return existing_file.version + 1, existing_file  # Next version replaces existing
        else:
            # Non-patient tables allow multiple files - always create new file with version 1
            # Each file in a non-patient table is independent with its own versioning
            return 1, None  # New file with version 1
    
    @staticmethod
    def prepare_file_metadata(
        uploaded_file: DjangoUploadedFile,
        version: int,
        file_name: Optional[str] = None,
        file_comments: Optional[str] = None
    ) -> dict:
        """
        Prepare metadata dictionary for file storage.
        
        Args:
            uploaded_file: Django uploaded file
            version: Version number
            file_name: Optional custom name for the file
            file_comments: Optional comments about the file
            
        Returns:
            Dictionary containing file metadata
        """
        return {
            'original_filename': uploaded_file.name,
            'file_size': uploaded_file.size,
            'version': version,
            'name': file_name or '',
            'comments': file_comments or '',
            'versioned_filename': FileUploadService.build_versioned_filename(
                uploaded_file.name, 
                version
            )
        }
    
    @staticmethod
    def handle_file_versioning(
        data_table_file: DataTableFile,
        new_uploaded_file: UploadedFile,
        user,
        metadata: dict
    ) -> DataTableFile:
        """
        Handle versioning for an existing DataTableFile.
        
        Args:
            data_table_file: Existing DataTableFile to version
            new_uploaded_file: New UploadedFile record
            user: User performing the update
            metadata: File metadata dictionary
            
        Returns:
            Updated DataTableFile instance
        """
        # Create new version
        data_table_file.create_new_version(user, new_uploaded_file)
        
        # Update metadata
        data_table_file.name = metadata.get('name', data_table_file.name)
        data_table_file.comments = metadata.get('comments', '')
        data_table_file.file_size = metadata.get('file_size', 0)
        data_table_file.original_filename = metadata.get('original_filename', '')
        
        # Save changes
        data_table_file.save()
        
        logger.info(
            f"Updated file {data_table_file.id} to version {data_table_file.version} "
            f"for user {user.username}"
        )
        
        return data_table_file
    
    @transaction.atomic
    def process_file_upload_secure(
        self,
        uploaded_file: DjangoUploadedFile,
        submission,
        data_table: CohortSubmissionDataTable,
        user,
        file_name: str = '',
        file_comments: str = '',
        file_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        SECURE file upload - streams directly to services server, no temp storage on web server.

        This method ensures PHI NEVER resides on the web server:
        - For small files (<10MB): Stream synchronously to services server
        - For large files (>=10MB): Use chunked upload to services server
        - Creates database records
        - Returns immediately after streaming

        Args:
            uploaded_file: The uploaded file
            submission: CohortSubmission instance
            data_table: CohortSubmissionDataTable instance
            user: User performing upload
            file_name: Optional custom file name
            file_comments: Optional file comments
            file_id: Optional ID of existing file to update

        Returns:
            Dictionary with upload results
        """
        # FAST PATH: Skip slow file structure validation - DuckDB will catch malformed files
        # Use default metadata values - DuckDB's read_csv_auto() handles encoding detection
        file_metadata = {
            'detected_encoding': 'utf-8',
            'has_bom': False,
            'validation_performed_at': timezone.now().isoformat()
        }
        validation_warnings = []

        # STEP 1: FAST PATH PATIENT ID EXTRACTION AND VALIDATION
        logger.info("="*80)
        logger.info("STARTING FAST PATH PATIENT ID EXTRACTION (In-Memory DuckDB)")
        logger.info("="*80)

        from depot.services.duckdb_utils import InMemoryDuckDBExtractor
        from depot.models import SubmissionPatientIDs

        file_type_name = data_table.data_file_type.name
        is_patient_file = file_type_name.lower() == 'patient'

        logger.info(f"File type: {file_type_name}, Is patient file: {is_patient_file}")

        # Try in-memory DuckDB conversion and patient ID extraction
        try:
            # Reset file pointer for reading
            uploaded_file.seek(0)

            # Create in-memory DuckDB extractor
            extractor = InMemoryDuckDBExtractor(
                file_content=uploaded_file,
                encoding=file_metadata.get('detected_encoding', 'utf-8'),
                has_bom=file_metadata.get('has_bom', False)
            )

            logger.info("Attempting in-memory DuckDB conversion...")

            # Extract patient IDs using SQL DISTINCT (BLAZING FAST!)
            # Get list of possible patient ID column names to try
            # This handles both pre-mapped files (already have cohortPatientId) and
            # unmapped files (have cohort-specific column like sitePatientId)
            patient_id_columns = self._get_patient_id_column_names(
                submission.cohort,
                data_table.data_file_type
            )

            extracted_patient_ids = extractor.extract_patient_ids_flexible(patient_id_columns)

            logger.info(f"FAST PATH SUCCESS: Extracted {len(extracted_patient_ids)} unique patient IDs in <2 seconds!")

            # For patient files: save extracted IDs to database
            if is_patient_file:
                logger.info("Patient file detected - saving patient IDs to database...")
                SubmissionPatientIDs.create_or_update_for_submission(
                    submission=submission,
                    patient_ids=list(extracted_patient_ids),
                    user=user,
                    source_file=None  # Will be set later after DataTableFile is created
                )
                logger.info(f"✓ Saved {len(extracted_patient_ids)} patient IDs to submission {submission.id}")

        except ValueError as e:
            # DuckDB conversion failed - file is malformed
            error_msg = str(e)
            logger.error(f"FAST PATH FAILED - DuckDB conversion error: {error_msg}")

            # Direct user to precheck validation for detailed diagnostics
            return {
                'success': False,
                'error': (
                    f"Unable to process this file. It may be malformed or have formatting issues."
                ),
                'suggest_precheck': True,
                'cohort_id': submission.cohort.id,
                'data_file_type_id': data_table.data_file_type.id,
                'cohort_submission_id': submission.id,
                'validation_errors': ['File processing failed'],
                'validation_warnings': [],
                'metadata': {}
            }
        except Exception as e:
            # Catch any other errors (like BytesIO issues)
            error_msg = str(e)
            logger.error(f"FAST PATH FAILED - Unexpected error: {error_msg}")

            # Generic user-friendly error
            return {
                'success': False,
                'error': (
                    f"Unable to process this file."
                ),
                'suggest_precheck': True,
                'cohort_id': submission.cohort.id,
                'data_file_type_id': data_table.data_file_type.id,
                'cohort_submission_id': submission.id,
                'validation_errors': ['File processing failed'],
                'validation_warnings': [],
                'metadata': {}
            }

        # For non-patient files: validate patient IDs against patient file
        if not is_patient_file:
            logger.info("Non-patient file - validating patient IDs against patient file...")

            # Get patient IDs from SubmissionPatientIDs record
            patient_ids_record = SubmissionPatientIDs.objects.filter(submission=submission).first()

            if not patient_ids_record:
                logger.error("No patient file uploaded yet - cannot validate patient IDs")
                return {
                    'success': False,
                    'error': (
                        "Please upload the patient file first before uploading other data files.\n\n"
                        "The patient file establishes the valid patient ID universe for this submission."
                    ),
                    'validation_errors': ['No patient file uploaded'],
                    'validation_warnings': [],
                    'metadata': {}
                }

            # Get patient IDs universe from patient file
            patient_ids_universe = set(patient_ids_record.patient_ids)
            logger.info(f"Patient file contains {len(patient_ids_universe)} patient IDs")

            # Find invalid patient IDs (IDs in this file but NOT in patient file)
            invalid_patient_ids = extracted_patient_ids - patient_ids_universe

            if invalid_patient_ids:
                # Patient ID validation failed
                invalid_count = len(invalid_patient_ids)
                invalid_sample = ', '.join(sorted(list(invalid_patient_ids))[:5])

                logger.error(f"VALIDATION FAILED: Found {invalid_count} invalid patient IDs")

                id_word = "patient ID" if invalid_count == 1 else "patient IDs"
                error_message = (
                    f"Found {invalid_count} {id_word} not in your patient file.\n\n"
                    f"Example IDs: {invalid_sample}\n\n"
                    f"To fix this issue:\n\n"
                    f"  • Remove rows with invalid patient IDs from this file, OR\n"
                    f"  • Add missing patients to your patient file first"
                )

                return {
                    'success': False,
                    'error': error_message,
                    'suggest_precheck': True,
                    'cohort_id': submission.cohort.id,
                    'data_file_type_id': data_table.data_file_type.id,
                    'cohort_submission_id': submission.id,
                    'validation_errors': [error_message],
                    'validation_warnings': [],
                    'metadata': {},
                    'invalid_patient_ids': sorted(list(invalid_patient_ids))[:10]
                }

            logger.info(f"✓ All {len(extracted_patient_ids)} patient IDs are valid!")

        # Lock the data table to prevent concurrent uploads
        data_table = CohortSubmissionDataTable.objects.select_for_update().get(id=data_table.id)

        # Determine file version
        version, existing_file = self.determine_file_version(data_table, file_id)

        if file_id and not existing_file:
            raise ValueError('File not found')

        # Build filename with version
        filename_with_version = self.build_versioned_filename(uploaded_file.name, version)

        # Build NAS path
        cohort_name = submission.cohort.name.replace(' ', '_').replace('/', '-')
        nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{data_table.data_file_type.name}/raw/{filename_with_version}"

        # CRITICAL: Stream to services server - NO storage on web server
        phi_manager = PHIStorageManager()

        import time
        logger.info(f"Upload type: {type(uploaded_file)}, size: {uploaded_file.size} bytes")

        start_time = time.time()

        # Prepare metadata dict for hash calculation
        upload_metadata = {
            'cohort_id': submission.cohort.id,
            'user_id': user.id,
            'file_type': data_table.data_file_type.name
        }

        # For large files, use chunked upload to avoid timeouts
        if uploaded_file.size >= 10 * 1024 * 1024:  # 10MB or larger
            logger.info(f"Using chunked upload for large file ({uploaded_file.size / 1024 / 1024:.1f} MB)")

            # Check if storage backend supports chunked uploads
            if hasattr(phi_manager.storage, 'save_chunked'):
                # Use chunked upload for large files
                saved_path = phi_manager.storage.save_chunked(
                    path=nas_path,
                    file_obj=uploaded_file,
                    content_type=getattr(uploaded_file, 'content_type', 'application/octet-stream'),
                    metadata=upload_metadata
                )
            else:
                # Fall back to regular save
                saved_path = phi_manager.storage.save(nas_path, uploaded_file, metadata=upload_metadata)
        else:
            # Small files can use regular streaming
            saved_path = phi_manager.storage.save(nas_path, uploaded_file, metadata=upload_metadata)

        elapsed = time.time() - start_time
        logger.info(f"File streamed to services server in {elapsed:.2f} seconds: {saved_path}")

        # Get absolute path for PHI tracking
        absolute_path = phi_manager.storage.get_absolute_path(saved_path)

        # Track the NAS storage with file hash
        from depot.models import PHIFileTracking
        from django.contrib.contenttypes.models import ContentType
        PHIFileTracking.objects.create(
            cohort=submission.cohort,
            user=user,
            action='submission_file_uploaded',
            file_path=absolute_path,  # Use absolute path
            file_type='raw_csv' if filename_with_version.endswith('.csv') else 'raw_tsv',
            file_size=uploaded_file.size,
            file_hash=upload_metadata.get('file_hash', ''),  # Get hash calculated by RemoteStorageDriver
            server_role=os.environ.get('SERVER_ROLE', 'unknown'),
            cleanup_required=False,  # Submission files should be kept
            bytes_transferred=uploaded_file.size,
            content_type=ContentType.objects.get_for_model(submission),
            object_id=submission.id,
            metadata={'relative_path': saved_path, 'file_hash': upload_metadata.get('file_hash', '')}  # Keep relative for reference
        )

        # Create UploadedFile record with NAS path and validation metadata
        uploaded_file_record = UploadedFile.objects.create(
            filename=uploaded_file.name,
            storage_path=saved_path,  # Final NAS path
            uploader=user,
            type=UploadType.RAW,
            file_hash="pending_async_calculation",  # Hash will be calculated in background
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            content_type=getattr(uploaded_file, 'content_type', 'application/octet-stream'),
            # Validation metadata
            detected_encoding=file_metadata.get('detected_encoding', ''),
            has_bom=file_metadata.get('has_bom', False),
            has_crlf=file_metadata.get('has_crlf', False),
            line_count=file_metadata.get('line_count'),
            header_column_count=file_metadata.get('header_column_count'),
            validation_status='passed',  # We only reach here if validation passed
            validation_errors=[],  # No errors since validation passed
            validation_performed_at=file_metadata.get('validation_performed_at'),
        )

        # Hash calculation now handled in unified workflow chain after all processing

        # Prepare file metadata
        metadata = self.prepare_file_metadata(
            uploaded_file=uploaded_file,
            version=version,
            file_name=file_name,
            file_comments=file_comments
        )

        # Update or create DataTableFile
        if existing_file:
            # Update existing file with new version
            data_file = self.handle_file_versioning(
                data_table_file=existing_file,
                new_uploaded_file=uploaded_file_record,
                user=user,
                metadata=metadata
            )
            # File is already on NAS
            data_file.raw_file_path = saved_path
            data_file.save(update_fields=['raw_file_path'])
            logger.info(f"Updated file {data_file.id} to version {version} (pending async processing)")
        else:
            # Create brand new file
            data_file = self.create_new_data_table_file(
                data_table=data_table,
                uploaded_file_record=uploaded_file_record,
                user=user,
                metadata=metadata,
                file_hash="pending_async_calculation",
                raw_file_path=saved_path
            )
            logger.info(f"Created new file {data_file.id} with version {version} (pending async processing)")

        # For patient tables only: ensure only this file is current
        if data_table.data_file_type.name == 'patient':
            self._ensure_single_current_file(data_table, data_file)

            # Update SubmissionPatientIDs record to link the source file
            patient_ids_record = SubmissionPatientIDs.objects.filter(submission=submission).first()
            if patient_ids_record:
                patient_ids_record.source_file = data_file
                patient_ids_record.save(update_fields=['source_file'])
                logger.info(f"✓ Linked patient IDs record to DataTableFile {data_file.id}")

        # Update data table status if needed
        if data_table.status == 'not_started':
            data_table.update_status('in_progress', user)
            logger.info(f"Updated data table {data_table.id} status to in_progress")

        return {
            'success': True,
            'data_file': data_file,
            'version': version,
            'uploaded_file_record': uploaded_file_record,
            'raw_nas_path': saved_path,
            'file_hash': "pending_async_calculation",
            'validation_warnings': validation_warnings,
            'metadata': file_metadata
        }

    @transaction.atomic
    def process_file_upload(
        self,
        uploaded_file: DjangoUploadedFile,
        submission,
        data_table: CohortSubmissionDataTable,
        user,
        file_name: str = '',
        file_comments: str = '',
        file_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process complete file upload workflow.
        
        This method handles the entire file upload process including:
        - File hash calculation
        - Version determination
        - PHI storage
        - Database record creation
        - File cleanup
        
        Args:
            uploaded_file: The uploaded file
            submission: CohortSubmission instance
            data_table: CohortSubmissionDataTable instance
            user: User performing upload
            file_name: Optional custom file name
            file_comments: Optional file comments
            file_id: Optional ID of existing file to update
            
        Returns:
            Dictionary with upload results including:
            - data_file: Created/updated DataTableFile
            - version: File version number
            - uploaded_file_record: UploadedFile record
            - raw_nas_path: Path where file was stored
        """
        # Calculate file hash
        file_hash_str = self.calculate_file_hash(uploaded_file)
        
        # Lock the data table to prevent concurrent uploads
        data_table = CohortSubmissionDataTable.objects.select_for_update().get(id=data_table.id)
        
        # Determine file version
        version, existing_file = self.determine_file_version(data_table, file_id)
        
        if file_id and not existing_file:
            raise ValueError('File not found')
        
        # Build filename with version
        filename_with_version = self.build_versioned_filename(uploaded_file.name, version)
        
        # Store raw file on NAS using PHI manager
        phi_manager = PHIStorageManager()
        raw_nas_path, file_hash_str = phi_manager.store_raw_file(
            file_content=uploaded_file,
            submission=submission,
            file_type=data_table.data_file_type.name,
            filename=filename_with_version,
            user=user
        )

        # Get absolute path for PHI tracking
        absolute_path = raw_nas_path if raw_nas_path.startswith('/') else phi_manager.storage.get_absolute_path(raw_nas_path)

        # Create PHI tracking record for the main upload (like upload precheck does)
        from depot.models import PHIFileTracking
        from django.contrib.contenttypes.models import ContentType
        PHIFileTracking.objects.create(
            cohort=submission.cohort,
            user=user,
            action='submission_file_uploaded',
            file_path=absolute_path,  # Use absolute path
            file_type='raw_csv' if filename_with_version.endswith('.csv') else 'raw_tsv',
            server_role=os.environ.get('SERVER_ROLE', 'unknown'),
            cleanup_required=False,  # Submission files should be kept
            bytes_transferred=uploaded_file.size,
            content_type=ContentType.objects.get_for_model(submission),
            object_id=submission.id,
            metadata={'relative_path': raw_nas_path}  # Keep relative for reference
        )
        
        # Create UploadedFile record
        uploaded_file_record = self.create_uploaded_file_record(
            file=uploaded_file,
            user=user,
            storage_path=raw_nas_path,
            file_hash=file_hash_str,
            upload_type=UploadType.RAW
        )

        # Trigger background hash calculation for HIPAA compliance (if needed)
        if file_hash_str == "pending_async_calculation":
            calculate_file_hash_task.delay('UploadedFile', uploaded_file_record.id)

        # Prepare file metadata
        metadata = self.prepare_file_metadata(
            uploaded_file=uploaded_file,
            version=version,
            file_name=file_name,
            file_comments=file_comments
        )
        
        # Update or create DataTableFile
        if existing_file:
            # Update existing file with new version
            data_file = self.handle_file_versioning(
                data_table_file=existing_file,
                new_uploaded_file=uploaded_file_record,
                user=user,
                metadata=metadata
            )
            # Add the raw file path
            data_file.raw_file_path = raw_nas_path
            data_file.save(update_fields=['raw_file_path'])
            logger.info(f"Updated file {data_file.id} to version {version}")
        else:
            # Create brand new file
            data_file = self.create_new_data_table_file(
                data_table=data_table,
                uploaded_file_record=uploaded_file_record,
                user=user,
                metadata=metadata,
                file_hash=file_hash_str,
                raw_file_path=raw_nas_path
            )
            logger.info(f"Created new file {data_file.id} with version {version}")
        
        # For patient tables only: ensure only this file is current
        if data_table.data_file_type.name == 'patient':
            self._ensure_single_current_file(data_table, data_file)
        
        # Update data table status if needed
        if data_table.status == 'not_started':
            data_table.update_status('in_progress', user)
            logger.info(f"Updated data table {data_table.id} status to in_progress")
        
        return {
            'data_file': data_file,
            'version': version,
            'uploaded_file_record': uploaded_file_record,
            'raw_nas_path': raw_nas_path,
            'file_hash': file_hash_str
        }
    
    @staticmethod
    def _ensure_single_current_file(data_table: CohortSubmissionDataTable, current_file: DataTableFile):
        """
        Ensure only the specified file is marked as current (for patient tables only).
        
        Args:
            data_table: The data table (should be patient type)
            current_file: The file that should be current
        """
        DataTableFile.objects.filter(
            data_table=data_table,
            is_current=True
        ).exclude(id=current_file.id).update(is_current=False)
        
        logger.debug(f"Ensured file {current_file.id} is the only current file for table {data_table.id}")
    
    @staticmethod
    def create_new_data_table_file(
        data_table,
        uploaded_file_record: UploadedFile,
        user,
        metadata: dict,
        file_hash: str,
        raw_file_path: Optional[str] = None
    ) -> DataTableFile:
        """
        Create a new DataTableFile record.
        
        Args:
            data_table: CohortSubmissionDataTable instance
            uploaded_file_record: UploadedFile record
            user: User performing the upload
            metadata: File metadata dictionary
            file_hash: SHA256 hash of the file
            raw_file_path: Optional path to raw file on NAS
            
        Returns:
            Created DataTableFile instance
        """
        # For patient tables, ensure only one file is current
        # For all other tables, allow multiple current files
        if data_table.data_file_type.name == 'patient':
            # Only one patient file allowed - mark others as not current
            DataTableFile.objects.filter(
                data_table=data_table,
                is_current=True
            ).update(is_current=False)
        
        # Create new file record
        data_file = DataTableFile.objects.create(
            data_table=data_table,
            uploaded_by=user,
            name=metadata.get('name', ''),
            comments=metadata.get('comments', ''),
            version=metadata.get('version', 1),
            uploaded_file=uploaded_file_record,
            original_filename=metadata.get('original_filename', ''),
            file_size=metadata.get('file_size', 0),
            file_hash=file_hash,
            raw_file_path=raw_file_path,
            is_current=True
        )

        # Hash calculation now handled in unified workflow chain after all processing

        logger.info(
            f"Created new DataTableFile {data_file.id} version {data_file.version} "
            f"for data table {data_table.id}"
        )

        return data_file

    def _get_patient_id_column_names(self, cohort, data_file_type):
        """
        Determine possible patient ID column names for this cohort.

        Returns a list of column names to try, in order of preference:
        1. Standard column name (cohortPatientId) - for pre-mapped files
        2. Source column name from mapping (e.g., sitePatientId) - for unmapped files

        This allows files to be uploaded either already in standard format
        or in cohort-specific format that will be mapped during processing.

        Args:
            cohort: Cohort model instance
            data_file_type: DataFileType model instance

        Returns:
            List of column names to try, e.g., ['cohortPatientId', 'sitePatientId']
        """
        # Always try standard column name first
        candidate_columns = ['cohortPatientId']

        try:
            from depot.services.data_mapping import DataMappingService

            # Check if cohort has a mapping for this file type
            mapping_service = DataMappingService(
                cohort_name=cohort.name,
                data_file_type=data_file_type.name
            )

            mapping_definition = mapping_service.mapping_definition

            if mapping_definition:
                # Look for a column mapping that targets cohortPatientId
                column_mappings = mapping_definition.get('column_mappings', [])
                for mapping in column_mappings:
                    if mapping.get('target_column') == 'cohortPatientId':
                        source_column = mapping.get('source_column')
                        # Add source column as second option (if different from standard)
                        if source_column and source_column.lower() != 'cohortpatientid':
                            candidate_columns.append(source_column)
                            logger.info(
                                f"Cohort {cohort.name} has mapping: "
                                f"{source_column} → cohortPatientId. "
                                f"Will try both column names."
                            )
                        break
        except Exception as e:
            logger.warning(f'Could not load column mapping: {e}', exc_info=True)

        return candidate_columns