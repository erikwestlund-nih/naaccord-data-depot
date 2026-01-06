"""
Data Mapping Service

Handles schema transformations for cohorts with non-standard data formats.
Reads JSON mapping definitions and transforms CSV data to standard schema.

Architecture:
- Registry maps cohort names to mapping groups
- Each group has per-file-type mapping definitions
- Supports column renames, value remaps, defaults, and pass-through

Usage:
    service = DataMappingService(cohort_name="UNC", data_file_type="patient")
    result = service.process_file(raw_csv_path, output_csv_path)
    # Returns changes_summary dict for DataProcessingLog
"""

import json
import logging
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class MappingNotFoundException(Exception):
    """Raised when a required mapping file is not found."""
    pass


class MappingValidationException(Exception):
    """Raised when mapping validation fails."""
    pass


class DataMappingService:
    """
    Service for transforming cohort data to standard schema.

    Reads JSON mapping definitions and applies column renames,
    value remaps, and default values to CSV files.
    """

    def __init__(self, cohort_name: str, data_file_type: str):
        """
        Initialize mapping service for a specific cohort and file type.

        Args:
            cohort_name: Name of cohort (e.g., "UNC", "Vanderbilt")
            data_file_type: Data file type name (e.g., "patient", "visit")
        """
        self.cohort_name = cohort_name
        self.data_file_type = data_file_type
        self.mappings_dir = Path(settings.BASE_DIR) / "depot" / "data" / "mappings"

        # Load registry and determine mapping group
        self.mapping_group = self._load_mapping_group()

        # Load mapping definition if not passthrough
        self.mapping_definition = None
        if self.mapping_group != 'passthrough':
            # Try to load mapping definition, but fall back to passthrough if not found
            self.mapping_definition = self._load_mapping_definition()
            if self.mapping_definition is None:
                # No mapping for this file type, use passthrough
                self.mapping_group = 'passthrough'

    def _load_mapping_group(self) -> str:
        """
        Load registry.json and determine mapping group for cohort.

        Returns:
            Mapping group name (e.g., "cnics") or "passthrough"
        """
        registry_path = self.mappings_dir / "registry.json"

        if not registry_path.exists():
            logger.warning(f"Registry not found at {registry_path}, using passthrough")
            return 'passthrough'

        try:
            with open(registry_path, 'r') as f:
                registry = json.load(f)

            mapping_group = registry.get('cohort_to_group', {}).get(self.cohort_name, 'passthrough')
            logger.info(f"Cohort '{self.cohort_name}' mapped to group '{mapping_group}'")
            return mapping_group

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse registry.json: {e}")
            return 'passthrough'

    def _load_mapping_definition(self) -> Dict:
        """
        Load mapping definition JSON for cohort group and file type.

        Falls back to _default.json if specific file type mapping doesn't exist.

        Returns:
            Mapping definition dictionary, or None if not found (will fall back to passthrough)

        Raises:
            MappingValidationException: If definition file exists but is malformed
        """
        # Try specific file type mapping first
        mapping_path = (
            self.mappings_dir /
            "cohort_groups" /
            self.mapping_group /
            f"{self.data_file_type}.json"
        )

        if not mapping_path.exists():
            # Try default mapping for this cohort group
            default_path = (
                self.mappings_dir /
                "cohort_groups" /
                self.mapping_group /
                "_default.json"
            )

            if default_path.exists():
                try:
                    with open(default_path, 'r') as f:
                        definition = json.load(f)

                    logger.info(
                        f"Using default mapping for {self.cohort_name}/{self.data_file_type} "
                        f"(loaded from {default_path})"
                    )
                    return definition

                except json.JSONDecodeError as e:
                    raise MappingValidationException(
                        f"Failed to parse default mapping definition {default_path}: {e}"
                    )
            else:
                logger.info(
                    f"No mapping definition for {self.cohort_name}/{self.data_file_type} "
                    f"(expected at {mapping_path} or {default_path}), will use passthrough mode"
                )
                return None

        try:
            with open(mapping_path, 'r') as f:
                definition = json.load(f)

            logger.info(f"Loaded mapping definition from {mapping_path}")
            return definition

        except json.JSONDecodeError as e:
            raise MappingValidationException(
                f"Failed to parse mapping definition {mapping_path}: {e}"
            )

    def is_passthrough(self) -> bool:
        """Check if this cohort uses passthrough (no transformation)."""
        return self.mapping_group == 'passthrough'

    def process_file(self, input_path: str, output_path: str) -> Dict:
        """
        Process CSV file through mapping transformation.

        Uses simple text operations (no pandas) for efficiency.
        Column renaming: simple text replacement on header row
        Value remapping: row-by-row processing if needed

        Args:
            input_path: Path to raw CSV file
            output_path: Path to write processed CSV

        Returns:
            changes_summary dict containing:
                - renamed_columns: List of column renames
                - value_remaps: Dict of value remapping operations
                - defaults_applied: Dict of default values applied
                - unmapped_columns: List of columns passed through
                - warnings: List of warning messages
                - errors: List of error messages
                - summary: Human-readable summary
        """
        # Clean file first (remove BOM, fix line endings)
        from depot.services.file_cleaner import FileCleanerService
        import tempfile

        # Create temporary cleaned file
        cleaned_fd, cleaned_path = tempfile.mkstemp(suffix='.csv', prefix='cleaned_')
        import os
        os.close(cleaned_fd)

        try:
            cleaning_result = FileCleanerService.clean_file(input_path, cleaned_path)
            if cleaning_result['had_bom'] or cleaning_result['had_crlf']:
                logger.info(f"Cleaned file: BOM={cleaning_result['had_bom']}, CRLF={cleaning_result['had_crlf']}")

            # Use cleaned file for processing
            processing_input = cleaned_path
        except Exception as e:
            logger.warning(f"File cleaning failed, using original: {e}")
            processing_input = input_path
            cleaning_result = None

        # Initialize changes summary
        changes_summary = {
            'renamed_columns': [],
            'value_remaps': {},
            'defaults_applied': {},
            'unmapped_columns': [],
            'warnings': [],
            'errors': [],
            'summary': {},
            'file_cleaning': cleaning_result
        }

        # Load data definition for normalization (needed for both passthrough and transform modes)
        from depot.data.definition_loader import get_definition_for_type
        try:
            definition = get_definition_for_type(self.data_file_type)
            definition_list = definition.get_definition()

            # Build case-insensitive map: lowercase -> correct casing
            definition_columns = {}
            for var_def in definition_list:
                col_name = var_def.get('name')
                definition_columns[col_name.lower()] = col_name
        except Exception as e:
            logger.warning(f"Could not load data definition for normalization: {e}")
            definition_columns = {}

        # If passthrough, normalize column names but don't apply mappings
        # OPTIMIZED: Stream line-by-line to handle large files (e.g., 1.9GB)
        if self.is_passthrough():
            try:
                row_count = 0
                normalized_count = 0
                header = None

                with open(processing_input, 'r', encoding='utf-8') as infile, \
                     open(output_path, 'w', encoding='utf-8', newline='') as outfile:

                    # Read and process header line only
                    header_line = infile.readline()
                    if not header_line:
                        changes_summary['errors'].append("File is empty")
                        return changes_summary

                    header_line = header_line.rstrip('\r\n')
                    header = next(csv.reader([header_line]))

                    # Normalize header column names
                    for i, col_name in enumerate(header):
                        col_lower = col_name.lower()
                        if col_lower in definition_columns:
                            correct_name = definition_columns[col_lower]
                            if col_name != correct_name:
                                header[i] = correct_name
                                normalized_count += 1
                                logger.debug(f"Normalized column casing: {col_name} → {correct_name}")

                    # Write normalized header
                    writer = csv.writer(outfile)
                    writer.writerow(header)

                    # Stream remaining lines directly (no CSV parsing, no memory load)
                    for line in infile:
                        outfile.write(line)
                        row_count += 1

                logger.info(f"Passthrough mode - normalized {normalized_count} columns, streamed {row_count} rows")
                changes_summary['summary'] = {
                    'mode': 'passthrough',
                    'rows_processed': row_count,
                    'columns_normalized': normalized_count,
                    'columns_original': len(header) if header else 0,
                    'columns_after': len(header) if header else 0
                }
                return changes_summary
            except Exception as e:
                changes_summary['errors'].append(f"Failed to copy file: {e}")
                return changes_summary

        # Build column rename map (case-insensitive matching)
        column_rename_map = {}  # lowercase source -> target
        column_mappings = self.mapping_definition.get('column_mappings', [])

        for mapping in column_mappings:
            source_col = mapping['source_column']
            target_col = mapping['target_column']
            column_rename_map[source_col.lower()] = target_col

        # Process CSV file
        try:
            with open(processing_input, 'r', newline='', encoding='utf-8') as infile, \
                 open(output_path, 'w', newline='', encoding='utf-8') as outfile:

                reader = csv.reader(infile)
                writer = csv.writer(outfile)

                # Process header row - case-insensitive matching + normalization
                header = next(reader)
                original_header = header.copy()
                renamed_count = 0
                normalized_count = 0

                for i, col_name in enumerate(header):
                    col_lower = col_name.lower()
                    original_name = col_name

                    # First check if it needs renaming (e.g., sitePatientId -> cohortPatientId)
                    if col_lower in column_rename_map:
                        header[i] = column_rename_map[col_lower]
                        renamed_count += 1
                        changes_summary['renamed_columns'].append({
                            'source': original_name,
                            'target': header[i]
                        })
                        logger.debug(f"Renamed column: {original_name} → {header[i]}")

                    # Then normalize casing to match data definition
                    elif col_lower in definition_columns:
                        correct_name = definition_columns[col_lower]
                        if col_name != correct_name:
                            header[i] = correct_name
                            normalized_count += 1
                            logger.debug(f"Normalized column casing: {col_name} → {correct_name}")

                writer.writerow(header)

                # Copy all data rows as-is (for now - value remapping can be added later)
                row_count = 0
                for row in reader:
                    writer.writerow(row)
                    row_count += 1

                logger.info(f"Processed {row_count} rows, renamed {renamed_count} columns, normalized {normalized_count} column casings")

                changes_summary['summary'] = {
                    'mode': 'transform',
                    'rows_processed': row_count,
                    'columns_renamed': renamed_count,
                    'columns_normalized': normalized_count,
                    'columns_original': len(original_header),
                    'columns_after': len(header)
                }

        except Exception as e:
            changes_summary['errors'].append(f"Failed to process file: {e}")
            logger.error(f"File processing failed: {e}", exc_info=True)
        finally:
            # Clean up temporary cleaned file
            if processing_input != input_path:
                try:
                    Path(cleaned_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temporary file {cleaned_path}: {e}")

        return changes_summary

    def get_mapping_info(self) -> Dict:
        """
        Get information about current mapping configuration.

        Returns:
            Dict with mapping metadata
        """
        return {
            'cohort_name': self.cohort_name,
            'data_file_type': self.data_file_type,
            'mapping_group': self.mapping_group,
            'is_passthrough': self.is_passthrough(),
            'has_definition': self.mapping_definition is not None
        }
