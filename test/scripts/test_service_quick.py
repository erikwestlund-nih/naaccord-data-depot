#!/usr/bin/env python
"""Quick test of FileUploadService to verify it works."""

import os
import sys
import django
import hashlib

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'depot.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from depot.services.file_upload_service import FileUploadService

def test_file_upload_service():
    """Quick tests of FileUploadService functionality."""
    service = FileUploadService()
    print("Testing FileUploadService...")
    
    # Test 1: Calculate file hash
    print("\n1. Testing file hash calculation...")
    content = b"Test file content"
    test_file = SimpleUploadedFile("test.csv", content)
    
    calculated_hash = service.calculate_file_hash(test_file)
    expected_hash = hashlib.sha256(content).hexdigest()
    
    assert calculated_hash == expected_hash, f"Hash mismatch: {calculated_hash} != {expected_hash}"
    print(f"   ✓ File hash: {calculated_hash[:16]}...")
    
    # Test 2: Build versioned filename
    print("\n2. Testing versioned filename...")
    versioned = service.build_versioned_filename("patient_data.csv", 3)
    assert versioned == "v3_patient_data.csv", f"Wrong versioned name: {versioned}"
    print(f"   ✓ Versioned filename: {versioned}")
    
    # Test 3: Build storage path
    print("\n3. Testing storage path...")
    path = service.build_storage_path(
        cohort_id=1,
        cohort_name="Test Cohort",
        protocol_year="2024",
        file_type="patient",
        filename="data.csv",
        is_attachment=False
    )
    expected_path = "1_Test_Cohort/2024/patient/data.csv"
    assert path == expected_path, f"Wrong path: {path}"
    print(f"   ✓ Storage path: {path}")
    
    # Test 4: Build attachment path
    print("\n4. Testing attachment path...")
    attach_path = service.build_storage_path(
        cohort_id=2,
        cohort_name="Another/Cohort",
        protocol_year="2025",
        file_type="laboratory",
        filename="notes.pdf",
        is_attachment=True
    )
    expected_attach = "2_Another-Cohort/2025/laboratory/attachments/notes.pdf"
    assert attach_path == expected_attach, f"Wrong attachment path: {attach_path}"
    print(f"   ✓ Attachment path: {attach_path}")
    
    # Test 5: Prepare metadata
    print("\n5. Testing metadata preparation...")
    test_file.size = 1234
    metadata = service.prepare_file_metadata(
        uploaded_file=test_file,
        version=2,
        file_name="Custom Name",
        file_comments="Test comments"
    )
    
    assert metadata['original_filename'] == 'test.csv'
    assert metadata['file_size'] == 1234
    assert metadata['version'] == 2
    assert metadata['name'] == 'Custom Name'
    assert metadata['comments'] == 'Test comments'
    assert metadata['versioned_filename'] == 'v2_test.csv'
    print(f"   ✓ Metadata prepared correctly")
    
    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    try:
        test_file_upload_service()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)