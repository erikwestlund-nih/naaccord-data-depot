"""
Unit tests for data processing service.

Tests the DataMappingService which handles:
- Column renaming (e.g., sitePatientId -> cohortPatientId)
- Case-insensitive column matching
- Column name normalization to data definition casing
"""
import tempfile
import os
from pathlib import Path
from django.test import TestCase
from django.db import connection

from depot.models import Cohort, DataFileType
from depot.services.data_mapping import DataMappingService


# Fixture: Patient CSV with CNICS cohort column names (sitePatientId instead of cohortPatientId)
PATIENT_CSV_CNICS = """sitePatientId,race,sex,ageinyrs
P001,1,M,45
P002,2,F,32
P003,1,M,28"""


# Fixture: Patient CSV with messy casing
PATIENT_CSV_MESSY_CASING = """COHORTPATIENTID,Race,presentSex,Hispanic
P001,1,M,N
P002,2,F,N
P003,1,M,Y"""


# Fixture: Patient CSV with CNICS column name in weird casing
PATIENT_CSV_CNICS_MESSY = """SitePatientID,RACE,sex,AGEINYRS
P001,1,M,45
P002,2,F,32
P003,1,M,28"""


class DataProcessingServiceColumnRenamingTest(TestCase):
    """Test column renaming for CNICS cohorts."""

    def setUp(self):
        """Create test fixtures."""
        # UNC is a CNICS cohort that uses sitePatientId instead of cohortPatientId
        self.cohort = Cohort.objects.create(name='UNC - Chapel Hill')
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_column_renaming_sitepatientid_to_cohortpatientid(self):
        """
        Test that sitePatientId is renamed to cohortPatientId for CNICS cohorts.

        CNICS cohorts (UNC, Vanderbilt, UCSD, UW, Fenway, UAB, Case Western, JHHCC)
        use sitePatientId in their raw data, which must be renamed to cohortPatientId.
        """
        # Create raw file with sitePatientId
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(PATIENT_CSV_CNICS)
            raw_path = raw_file.name

        # Create processed file path
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Process through DataMappingService
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )

            # Process the file
            changes = service.process_file(raw_path, processed_path)

            # Verify no errors
            self.assertEqual(len(changes['errors']), 0, "Processing should complete without errors")

            # Verify column was renamed
            self.assertEqual(len(changes['renamed_columns']), 1, "Should have renamed 1 column")
            self.assertEqual(changes['renamed_columns'][0]['source'], 'sitePatientId')
            self.assertEqual(changes['renamed_columns'][0]['target'], 'cohortPatientId')

            # Verify processed file has correct header
            with open(processed_path, 'r') as f:
                header = f.readline().strip()

            self.assertIn('cohortPatientId', header, "Processed file should have cohortPatientId column")
            self.assertNotIn('sitePatientId', header, "Processed file should NOT have sitePatientId column")

            # Verify data is preserved
            with open(processed_path, 'r') as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 4, "Should have header + 3 data rows")
            self.assertIn('P001', lines[1])
            self.assertIn('P002', lines[2])
            self.assertIn('P003', lines[3])

        finally:
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)

    def test_case_insensitive_column_matching(self):
        """
        Test that column renaming works with case-insensitive matching.

        If the uploaded file has SitePatientID or SITEPATIENTID, it should
        still match sitePatientId in the mapping and get renamed to cohortPatientId.
        """
        # Create raw file with weird casing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(PATIENT_CSV_CNICS_MESSY)
            raw_path = raw_file.name

        # Create processed file path
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Process through DataMappingService
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )

            changes = service.process_file(raw_path, processed_path)

            # Verify no errors
            self.assertEqual(len(changes['errors']), 0)

            # Verify column was renamed despite casing difference
            self.assertEqual(len(changes['renamed_columns']), 1)
            self.assertEqual(changes['renamed_columns'][0]['source'], 'SitePatientID')
            self.assertEqual(changes['renamed_columns'][0]['target'], 'cohortPatientId')

            # Verify processed file has correct header
            with open(processed_path, 'r') as f:
                header = f.readline().strip()

            self.assertIn('cohortPatientId', header)
            self.assertNotIn('SitePatientID', header)
            self.assertNotIn('sitePatientId', header)

        finally:
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)


class DataProcessingServiceNormalizationTest(TestCase):
    """Test column name normalization to data definition casing."""

    def setUp(self):
        """Create test fixtures."""
        # Use a non-CNICS cohort for normalization testing (passthrough mapping)
        self.cohort = Cohort.objects.create(name='Test Cohort')
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_column_name_normalization(self):
        """
        Test that column names are normalized to match data definition casing.

        If the upload has COHORTPATIENTID or Race, it should be normalized
        to cohortPatientId and race to match the data definition.
        """
        # Create raw file with messy casing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(PATIENT_CSV_MESSY_CASING)
            raw_path = raw_file.name

        # Create processed file path
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Process through DataMappingService
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )

            changes = service.process_file(raw_path, processed_path)

            # Verify no errors
            self.assertEqual(len(changes['errors']), 0)

            # Verify columns were normalized
            self.assertGreater(
                changes['summary'].get('columns_normalized', 0),
                0,
                "Should have normalized at least one column"
            )

            # Verify processed file has correct normalized casing
            with open(processed_path, 'r') as f:
                header = f.readline().strip()

            # Should match data definition casing exactly
            self.assertIn('cohortPatientId', header)
            self.assertIn('race', header)
            self.assertIn('presentSex', header)
            self.assertIn('hispanic', header)

            # Should NOT have messy casing
            self.assertNotIn('COHORTPATIENTID', header)
            self.assertNotIn('Race', header)
            self.assertNotIn('Hispanic', header)

            # Verify data is preserved
            with open(processed_path, 'r') as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 4)
            self.assertIn('P001', lines[1])

        finally:
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)


class DataProcessingServicePassthroughTest(TestCase):
    """Test passthrough mode for cohorts without custom mappings."""

    def setUp(self):
        """Create test fixtures."""
        self.cohort = Cohort.objects.create(name='Test Cohort')
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_passthrough_mode_copies_file(self):
        """
        Test that cohorts without custom mappings use passthrough mode.

        Passthrough mode should copy the file as-is (with normalization).
        """
        # Create raw file
        raw_content = """cohortPatientId,race,sex,ageinyrs
P001,1,M,45
P002,2,F,32"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(raw_content)
            raw_path = raw_file.name

        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )

            # Verify it's passthrough mode
            self.assertTrue(service.is_passthrough())

            changes = service.process_file(raw_path, processed_path)

            # Verify no errors
            self.assertEqual(len(changes['errors']), 0)

            # Verify mode is passthrough
            self.assertEqual(changes['summary'].get('mode'), 'passthrough')

            # Verify file was copied
            self.assertTrue(os.path.exists(processed_path))

            with open(processed_path, 'r') as f:
                processed_content = f.read()

            # CSV writer adds trailing newline, so strip for comparison
            self.assertEqual(processed_content.rstrip('\n'), raw_content.rstrip('\n'))

        finally:
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)


class DataProcessingServiceCNICSCohortsTest(TestCase):
    """Test that all CNICS cohorts use the correct mapping group."""

    def setUp(self):
        """Create test fixtures."""
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_all_cnics_cohorts_use_mapping(self):
        """
        Test that all CNICS cohorts are mapped to the 'cnics' transformation group.

        CNICS cohorts: UNC - Chapel Hill, Vanderbilt, UCSD, UW - Seattle, Fenway, UA - Birmingham, CWRU, JHHCC
        """
        cnics_cohorts = [
            'UNC - Chapel Hill', 'Vanderbilt', 'UCSD', 'UW - Seattle', 'Fenway', 'UA - Birmingham', 'CWRU', 'JHHCC'
        ]

        for cohort_name in cnics_cohorts:
            service = DataMappingService(
                cohort_name=cohort_name,
                data_file_type=self.data_file_type.name
            )

            # Verify not passthrough
            self.assertFalse(
                service.is_passthrough(),
                f"{cohort_name} should NOT use passthrough mode"
            )

            # Verify mapping group is 'cnics'
            self.assertEqual(
                service.mapping_group,
                'cnics',
                f"{cohort_name} should be mapped to 'cnics' group"
            )
