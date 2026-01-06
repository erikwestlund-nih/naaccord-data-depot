#!/bin/bash

# Script to process REMAINING test data files using DuckDB for speed
# This processes only files not yet in valid/invalid directories

# Activate virtual environment
source venv/bin/activate

# Base directories
TEST_DIR="/Users/erikwestlund/code/naaccord/resources/data/test"
VALID_DIR="$TEST_DIR/valid"
INVALID_DIR="$TEST_DIR/invalid"

# Patient files
PATIENT_FULL="$TEST_DIR/patient/patient_sim_data_full_length.csv"
PATIENT_VALUES="$TEST_DIR/patient/patient_sim_data_values_only.csv"

# Files still to process (based on what's missing from valid dir)
REMAINING_FILES=(
    "discharge_dx_sim_data_values_only"
    "encounter_sim_data_full_length"
    "encounter_sim_data_values_only"
    "geographic_sim_data_full_length"
    "geographic_sim_data_values_only"
    "lab_sim_data_full_length"
    "lab_sim_data_values_only"
    "medication_sim_data_full_length"
    "medication_sim_data_values_only"
    "prodecure_sim_data_full_length"
    "prodecure_sim_data_values_only"
)

echo "Processing remaining test data files with DuckDB..."
echo "================================================"
echo ""

# Track timing
START_TIME=$(date +%s)

for FILE_BASE in "${REMAINING_FILES[@]}"; do
    echo "Processing $FILE_BASE..."

    # Determine if it's full_length or values_only
    if [[ $FILE_BASE == *"_full_length" ]]; then
        FILE_PREFIX="${FILE_BASE%_full_length}"
        FILE_TYPE="full_length"
        PATIENT_FILE="$PATIENT_FULL"
        DUPLICATE_FACTOR=20
    else
        FILE_PREFIX="${FILE_BASE%_values_only}"
        FILE_TYPE="values_only"
        PATIENT_FILE="$PATIENT_VALUES"
        DUPLICATE_FACTOR=5
    fi

    INPUT_FILE="$TEST_DIR/${FILE_BASE}.csv"

    if [ ! -f "$INPUT_FILE" ]; then
        echo "  Skipping - file not found: $INPUT_FILE"
        continue
    fi

    # Get file size for logging
    FILE_SIZE=$(ls -lh "$INPUT_FILE" | awk '{print $5}')
    echo "  File size: $FILE_SIZE"

    # Process valid version
    echo "  Creating valid version..."
    python manage.py remap_patient_ids_duckdb \
        --patient-file "$PATIENT_FILE" \
        --data-file "$INPUT_FILE" \
        --output "$VALID_DIR/${FILE_BASE}.csv" \
        --duplicate-factor $DUPLICATE_FACTOR \
        --seed 42 2>&1 | grep -E "Successfully" | tail -1

    # Process invalid version (10% invalid)
    echo "  Creating invalid version (10% invalid)..."
    python manage.py remap_patient_ids_duckdb \
        --patient-file "$PATIENT_FILE" \
        --data-file "$INPUT_FILE" \
        --output "$INVALID_DIR/${FILE_BASE}.csv" \
        --duplicate-factor $DUPLICATE_FACTOR \
        --invalid-ratio 0.1 \
        --seed 43 2>&1 | grep -E "Successfully" | tail -1

    echo ""
done

# Calculate total time
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo "================================================"
echo "Processing complete!"
echo "Total time: ${MINUTES}m ${SECONDS}s"
echo ""
echo "Files created:"
echo "Valid directory:"
ls -lh "$VALID_DIR"/*.csv 2>/dev/null | awk '{print "  " $9 ": " $5}'
echo ""
echo "Invalid directory:"
ls -lh "$INVALID_DIR"/*.csv 2>/dev/null | awk '{print "  " $9 ": " $5}'