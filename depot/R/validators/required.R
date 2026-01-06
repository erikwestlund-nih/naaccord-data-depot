#' Validate that a column contains no NULL values or empty strings
#' 
#' @param duckdb_conn DuckDB connection object
#' @param table_name Name of the table to validate (default: "data")
#' @param var Name of the column to validate
#' @param params Additional parameters (not used for required validation)
#' 
#' @return A standardized validation result
validate_required <- function(duckdb_conn, table_name = "data", var, params) {
  # First get total row count
  count_query <- sprintf("SELECT COUNT(*) as total FROM %s", table_name)
  total_rows <- DBI::dbGetQuery(duckdb_conn, count_query)$total
  
  # Check for NULL values and empty strings
  query <- sprintf("
    SELECT row_no, %s as value
    FROM %s
    WHERE %s IS NULL 
       OR TRIM(%s) = ''
  ", var, table_name, var, var)
  
  result <- DBI::dbGetQuery(duckdb_conn, query)
  
  # Check if we found any invalid rows
  if (nrow(result) > 0) {
    # Create a catalog of invalid values
    invalid_catalog <- create_invalid_catalog(result)
    
    # Calculate summary statistics
    summary_stats <- calculate_validation_summary(total_rows, result, invalid_catalog)
    
    # Count NULL values and empty strings separately
    null_count <- sum(is.na(result$value))
    empty_count <- nrow(result) - null_count
    
    # Build message based on what we found
    message_parts <- character()
    if (null_count > 0) {
      message_parts <- c(message_parts, sprintf("%d NULL values", null_count))
    }
    if (empty_count > 0) {
      message_parts <- c(message_parts, sprintf("%d empty strings", empty_count))
    }
    
    return(create_app_validation_result(
      validator_name = "required",
      valid = FALSE,
      message = sprintf(
        "Column '%s' contains %s (%s%%)", 
        var,
        paste(message_parts, collapse = " and "),
        summary_stats$invalid_percent
      ),
      invalid_rows = result,
      invalid_catalog = invalid_catalog,
      summary = summary_stats
    ))
  }
  
  # All values are valid
  return(create_app_validation_result(
    validator_name = "required",
    valid = TRUE,
    message = "All values are present",
    summary = calculate_validation_summary(total_rows, data.frame(), list())
  ))
}
