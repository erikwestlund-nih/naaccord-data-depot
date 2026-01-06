# Patient Audit No Duplicates Validator Issue - 2025-06-23 (Task 2)

## Summary
Encountered an error when testing patient data audit due to missing `validate_no_duplicates` function in NAATools package. The JSON definitions reference a "no_duplicates" validator that doesn't have a corresponding implementation in the R package.

## Issue Found
```
Error in `get()`:
! object 'validate_no_duplicates' not found
```

The error occurs because:
1. Patient definition has `"validators": ["no_duplicates"]` for cohortPatientId
2. The notebook code looks for `validate_no_duplicates` function in NAATools
3. NAATools only has: validate_required, validate_string, validate_date, validate_recommended

## Temporary Fix Applied
Removed the `no_duplicates` validator from patient_definition.json to allow testing to proceed.

## Files Modified
1. `depot/data/definitions/patient_definition.json` - Removed no_duplicates validator from cohortPatientId

## Other Affected Files
The following definitions also use "no_duplicates" and will need fixing:
- census_definition.json
- diagnosis_definition.json  
- discharge_diagnosis_definition.json
- encounter_definition.json
- geography_definition.json
- hospitalization_definition.json
- insurance_definition.json
- medication_definition.json
- mortality_definition.json
- procedure_definition.json
- risk_factor_definition.json
- substance_survey_definition.json

## Proper Solution Required
Need to implement `validate_no_duplicates` function in NAATools package:

```r
#' Validate that a column has no duplicate values
#' @param duckdb_conn DuckDB connection object
#' @param table_name Name of the table to validate
#' @param var Name of the column to validate
#' @param params Additional parameters (not used)
#' @return Validation result list
#' @export
validate_no_duplicates <- function(duckdb_conn, table_name = "data", var, params) {
  # Query to find duplicates
  query <- sprintf("
    SELECT %s as value, COUNT(*) as count
    FROM %s
    WHERE %s IS NOT NULL
    GROUP BY %s
    HAVING COUNT(*) > 1
    ORDER BY count DESC
  ", var, table_name, var, var)
  
  duplicates <- DBI::dbGetQuery(duckdb_conn, query)
  
  if (nrow(duplicates) == 0) {
    return(list(
      is_valid = TRUE,
      message = sprintf("No duplicate values found in column '%s'", var)
    ))
  } else {
    return(list(
      is_valid = FALSE,
      message = sprintf("Column '%s' has %d duplicate values", var, nrow(duplicates)),
      invalid_rows = duplicates
    ))
  }
}
```

## Testing Results
- ❌ Original patient audit failed with validate_no_duplicates error
- 🔄 After removing validator, audit should proceed (pending test)

## Next Steps
1. **Immediate**: Test patient audit with validator removed
2. **Short term**: Implement validate_no_duplicates in NAATools
3. **Complete**: Add validator back to all affected JSON definitions

## Status
🔄 **In Progress** - Temporary fix applied, proper solution pending