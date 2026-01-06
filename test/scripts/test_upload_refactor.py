#!/usr/bin/env python
"""
Test script to verify the refactored upload functionality works correctly.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'depot.settings')
django.setup()

from django.test import RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from depot.models import (
    Cohort, ProtocolYear, DataFileType,
    CohortSubmission, CohortSubmissionDataTable
)
from depot.views.submissions.table_manage import handle_ajax_file_upload
import json

User = get_user_model()

def test_refactored_upload():
    """Test that the refactored upload handler still works."""
    print("Testing refactored upload functionality...")
    
    # Setup test data
    print("\n1. Setting up test data...")
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("   ❌ No superuser found. Please create one first.")
        return False
    print(f"   ✓ Using user: {user.username}")
    
    # Get or create test cohort
    cohort, _ = Cohort.objects.get_or_create(
        name='Test Cohort',
        defaults={'code': 'TEST'}
    )
    print(f"   ✓ Using cohort: {cohort.name}")
    
    # Get or create protocol year
    protocol_year, _ = ProtocolYear.objects.get_or_create(year='2024')
    print(f"   ✓ Using protocol year: {protocol_year.year}")
    
    # Get patient file type
    file_type = DataFileType.objects.filter(name='patient').first()
    if not file_type:
        file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data',
            order=1
        )
    print(f"   ✓ Using file type: {file_type.name}")
    
    # Create submission
    submission = CohortSubmission.objects.create(
        cohort=cohort,
        protocol_year=protocol_year,
        status='in_progress',
        started_by=user
    )
    print(f"   ✓ Created submission: {submission.id}")
    
    # Create data table
    data_table = CohortSubmissionDataTable.objects.create(
        submission=submission,
        data_file_type=file_type,
        status='not_started'
    )
    print(f"   ✓ Created data table: {data_table.id}")
    
    # Test upload
    print("\n2. Testing file upload with FileUploadService...")
    
    # Create a test file
    test_content = b"cohortPatientId,birthYear,gender\nP001,1980,M\nP002,1975,F"
    test_file = SimpleUploadedFile(
        "test_patient_data.csv",
        test_content,
        content_type="text/csv"
    )
    
    # Create request
    factory = RequestFactory()
    request = factory.post('/upload/', {
        'file_name': 'Test Patient File',
        'file_comments': 'This is a test comment from refactored code'
    })
    request.FILES['file'] = test_file
    request.user = user
    request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
    
    # Call the refactored handler
    try:
        response = handle_ajax_file_upload(
            request,
            submission,
            data_table,
            is_patient_table=True,
            patient_file_exists=False
        )
        
        # Check response
        if hasattr(response, 'content'):
            content = json.loads(response.content)
            if content.get('success'):
                print(f"   ✓ Upload successful!")
                print(f"   ✓ File ID: {content.get('file_id')}")
                print(f"   ✓ Comments preserved: {content.get('comments')}")
                
                # Verify the file was created
                from depot.models import DataTableFile
                uploaded_file = DataTableFile.objects.get(id=content.get('file_id'))
                print(f"\n3. Verifying uploaded file...")
                print(f"   ✓ File name: {uploaded_file.name}")
                print(f"   ✓ Comments: {uploaded_file.comments}")
                print(f"   ✓ Version: {uploaded_file.version}")
                print(f"   ✓ File hash: {uploaded_file.file_hash[:16]}...")
                
                # Cleanup
                print(f"\n4. Cleaning up test data...")
                submission.delete()  # This will cascade delete
                print(f"   ✓ Test data cleaned up")
                
                return True
            else:
                print(f"   ❌ Upload failed: {content.get('error')}")
                return False
        else:
            print(f"   ❌ Unexpected response type")
            return False
            
    except Exception as e:
        print(f"   ❌ Error during upload: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_refactored_upload()
    if success:
        print("\n✅ Refactoring test passed! The FileUploadService integration works correctly.")
    else:
        print("\n❌ Refactoring test failed. Please check the implementation.")
    sys.exit(0 if success else 1)