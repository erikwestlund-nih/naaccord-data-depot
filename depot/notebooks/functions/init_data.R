#' Initialize shared data object for audit notebooks
#'
#' @param definition_file Path to the definition JSON file (relative to depot/data/definitions or fully qualified)
#' @param data_file_path Path to the DuckDB data file
#' @return A list containing:
#'   \item{definition}{The parsed definition JSON}
#'   \item{data_file_path}{Path to the data file}
#'   \item{db_stats}{Database statistics including row count and column types}
#'   \item{col_stats}{Data frame with column statistics including missing values, uniqueness, and cardinality}
#' @examples
#' d <- init_audit_data(
#'   definition_file = "laboratory_definition.json",
#'   data_file_path = "path/to/data.duckdb"
#' )
init_audit_data <- function(definition_file, data_file_path) {
  # Initialize shared data object
  d <- list()
  
  # Read definition and data
  tryCatch({
    # Read definition file - handle both relative and fully qualified paths
    definition_path <- if (file.exists(definition_file)) {
      definition_file  # Use as-is if it's a fully qualified path
    } else {
      here::here("depot", "data", "definitions", definition_file)  # Look in depot/data/definitions
    }
    d$definition <- NAATools::read_definition(definition_path)
    d$data_file_path <- data_file_path
    
    # Get database statistics
    d$db_stats <- NAATools::get_duckdb_stats(d$data_file_path, "data")
    z <- d$db_stats
    # Get column statistics
    d$col_stats <- calculate_column_stats(d$db_stats, d$definition)
    
    # Add metadata
    d$metadata <- create_metadata(
      definition_file = definition_file,
      data_file_path = data_file_path,
      row_count = d$db_stats$row_count,
      column_count = nrow(d$col_stats)
    )
    
    return(d)
  }, error = function(e) {
    stop(sprintf("Error initializing audit data: %s", e$message))
  })
}
