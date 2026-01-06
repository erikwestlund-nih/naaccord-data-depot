# Test Directory

This directory contains test utilities, scripts, and data for the NA-ACCORD project.

## Structure

```
test/
├── scripts/          # Test execution scripts
│   ├── run_all_tests.sh           # Run all tests with coverage
│   ├── run_service_tests.py       # Run service tests specifically
│   ├── test_service_quick.py      # Quick service test runner
│   └── test_upload_refactor.py    # Test upload refactoring
└── data/            # Test data files
    └── test_patient.csv           # Sample patient data for testing
```

## Running Tests

### From project root:

```bash
# Run all Django tests
python manage.py test --settings=depot.test_settings

# Run service tests only
python manage.py test depot.tests.services --settings=depot.test_settings

# Run with coverage
./test/scripts/run_all_tests.sh
```

### Using test scripts:

```bash
# Run all tests with coverage report
./test/scripts/run_all_tests.sh

# Quick service tests
python test/scripts/test_service_quick.py

# Test upload functionality
python test/scripts/test_upload_refactor.py
```

## Test Settings

Tests use `depot.test_settings` which configures:
- In-memory SQLite database
- Disabled migrations for speed
- MD5 password hasher for performance
- Mock external services

## Test Data

The `test/data/` directory contains sample CSV files for testing:
- `test_patient.csv` - Sample patient data with PHI fields

## Note

These test scripts were moved from the project root on 2025-01-22 to keep the root directory clean and organize testing utilities.