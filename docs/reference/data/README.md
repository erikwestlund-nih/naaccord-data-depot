# Data Directory

## Important: Test Data Management

The `test/` directory contains large test data files (12GB+) that should NOT be committed to the repository.

### Setup Instructions

1. **Test data is git-ignored** - The `test/` directory is excluded from version control
2. **Archive test data separately** - Store these files in a separate backup location
3. **Docker builds will be smaller** - Without test data, container images will be manageable size

### Test Data Files

The test directory contains full-length simulation data files:
- `*_sim_data_full_length.csv` files (100MB+ each)
- Multiple copies in `valid/`, `invalid/`, and other subdirectories

### Why This Matters

Including test data in Docker builds results in:
- 26GB+ container images (instead of ~2GB)
- Slow build times
- Excessive disk usage
- Registry storage issues

### Restoring Test Data

If you need the test data files:
1. Restore from your archive/backup location
2. Place in `resources/data/test/`
3. Files will be available locally but won't be committed to git or included in Docker builds