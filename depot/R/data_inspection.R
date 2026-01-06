#' Summarize the data file definition, validation rules, and provided data file (no patient data)
#' @param data_file_path Path to the DuckDB file
#' @param definition The definition list (as returned by read_definition)
#' @param table_name Name of the table in DuckDB (default: "data")
#' @return A data frame with column names and types
#' @export
summarize_data_file <- function(data_file_path, definition, table_name = "data") {
  # Build the full data file path using here()
  full_data_path <- do.call(here::here, as.list(data_file_path))

  # Connect to DuckDB
  con <- NAATools::open_duckdb_connection(full_data_path)
  on.exit(NAATools::close_duckdb_connection(con))

  tables <- DBI::dbListTables(con)
  if (!(table_name %in% tables)) {
    stop(sprintf("Table '%s' not found in DuckDB database. Available tables: %s", table_name, paste(tables, collapse = ", ")))
  }

  # Get column info using PRAGMA table_info
  col_info <- DBI::dbGetQuery(con, sprintf("PRAGMA table_info('%s')", table_name))

  # Create a named vector for quick lookup of types from the definition
  def_types <- setNames(
    sapply(definition, function(var) if (!is.null(var$type)) var$type else ""),
    sapply(definition, function(var) var$name)
  )

  # Filter out the row_no column
  col_info <- col_info[col_info$name != "row_no", ]

  # Return a data frame with column names from DuckDB, types from the definition
  data.frame(
    name = col_info$name,
    type = as.character(def_types[col_info$name]),
    stringsAsFactors = FALSE
  )
}

#' Summarize the audit information for a data file
#' @param data_file_name Name of the data file
#' @param data_file_path Path to the DuckDB file
#' @param definition_path Path to the definition file
#' @param table_name Name of the table in DuckDB (default: "data")
#' @export
summarize_audit <- function(data_file_name, data_file_path, definition_path, table_name = "data") {
  # Check that the DuckDB file exists
  full_data_path <- do.call(here::here, as.list(data_file_path))
  if (!file.exists(full_data_path)) {
    stop(sprintf("DuckDB file not found at: %s", full_data_path))
  }

  # Read the definition
  def <- NAATools::read_definition(definition_path)

  # Get data file summary (column names/types only, no data)
  data_summary <- summarize_data_file(data_file_path, def, table_name)

  # Get definition summary
  def_summary <- NAATools::summarize_definition(def)

  cat("### Data File Definition\n")
  print(knitr::kable(def_summary, caption = paste(data_file_name, "Definition")))
  cat("\n\n")

  cat("### Provided Data File Summary\n")
  print(knitr::kable(data_summary, caption = paste(data_file_name, "Data File Summary")))
  cat("\n\n")
}

#' Calculate column statistics for a dataset
#'
#' @param db_stats Database statistics from get_duckdb_stats
#' @param definition Variable definitions
#' @return A data frame with column statistics
calculate_column_stats <- function(db_stats, definition) {
  data.frame(
    "Variable" = db_stats$column_types$column_name,
    "Type" = sapply(db_stats$column_types$column_name, function(col) {
      if (col %in% names(definition)) definition[[col]]$type else "not specified"
    }),
    "Missing (N)" = sapply(db_stats$column_types$column_name, function(col) {
      db_stats$column_stats[[col]]$nulls
    }),
    "%" = sprintf("%.1f", sapply(
      db_stats$column_types$column_name,
      function(col) db_stats$column_stats[[col]]$nulls / db_stats$row_count * 100
    )),
    "Unique" = sapply(
      db_stats$column_types$column_name,
      function(col) db_stats$column_stats[[col]]$unique_values
    ),
    "Cardinality" = sapply(
      db_stats$column_types$column_name,
      function(col) {
        pct <- db_stats$column_stats[[col]]$unique_values / db_stats$row_count * 100
        if (pct > 90) {
          sprintf("High (%.1f%%)", pct)
        } else if (pct > 1) {
          sprintf("Medium (%.1f%%)", pct)
        } else {
          sprintf("Low (%.1f%%)", pct)
        }
      }
    ),
    stringsAsFactors = FALSE
  )[db_stats$column_types$column_name != "row_no", ]
}