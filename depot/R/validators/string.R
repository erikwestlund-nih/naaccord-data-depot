#' Validate that a column contains only string values
#' 
#' @param duckdb_conn DuckDB connection object
#' @param table_name Name of the table to validate (default: "data")
#' @param var Name of the column to validate
#' @param params Additional parameters (not used for string validation)
#' 
#' @return A standardized validation result
validate_string <- function(duckdb_conn, table_name = "data", var, params) {
  # First get total row count
  count_query <- sprintf("SELECT COUNT(*) as total FROM %s", table_name)
  total_rows <- DBI::dbGetQuery(duckdb_conn, count_query)$total
  
  # Use DuckDB's TRY_CAST to attempt string conversion
  # This will return NULL for any values that can't be cast to string
  query <- sprintf("
    SELECT row_no, %s as value
    FROM %s
    WHERE TRY_CAST(%s AS VARCHAR) IS NULL
  ", var, table_name, var)
  
  result <- DBI::dbGetQuery(duckdb_conn, query)
  
  # Check if we found any invalid rows
  if (nrow(result) > 0) {
    # Create a catalog of invalid values
    invalid_catalog <- create_invalid_catalog(result)
    
    # Calculate summary statistics
    summary_stats <- calculate_validation_summary(total_rows, result, invalid_catalog)
    
    # Count NA values separately
    na_count <- sum(is.na(result$value))
    non_na_count <- nrow(result) - na_count
    
    # Build message based on what we found
    message_parts <- character()
    if (na_count > 0) {
      message_parts <- c(message_parts, sprintf("%d NULL values", na_count))
    }
    if (non_na_count > 0) {
      message_parts <- c(message_parts, sprintf("%d non-string values", non_na_count))
    }
    
    return(create_app_validation_result(
      validator_name = "string",
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
  
  # All values are valid strings
  return(create_app_validation_result(
    validator_name = "string",
    valid = TRUE,
    message = "All values are valid strings",
    summary = calculate_validation_summary(total_rows, data.frame(), list())
  ))
}