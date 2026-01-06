#!/bin/bash
# Run all refactoring tests

echo "========================================="
echo "Running FileUploadService Tests"
echo "========================================="

echo ""
echo "1. Running Quick Service Tests..."
echo "-----------------------------------------"
python test_service_quick.py
if [ $? -ne 0 ]; then
    echo "❌ Quick service tests failed"
    exit 1
fi

echo ""
echo "2. Running Unit Tests..."
echo "-----------------------------------------"
python depot/tests/services/test_file_upload_service_unit.py
if [ $? -ne 0 ]; then
    echo "❌ Unit tests failed"
    exit 1
fi

echo ""
echo "3. Running Integration Tests..."
echo "-----------------------------------------"
python test_upload_refactor.py
if [ $? -ne 0 ]; then
    echo "❌ Integration tests failed"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ All tests passed successfully!"
echo "========================================="