#' Create metadata for a dataset
#'
#' @param definition_file Path to the definition file
#' @param data_file_path Path to the data file
#' @param row_count Number of rows in the dataset
#' @param column_count Number of columns in the dataset
#' @return A list containing metadata information
create_metadata <- function(definition_file, data_file_path, row_count, column_count) {
  list(
    created_at = Sys.time(),
    row_count = row_count,
    column_count = column_count,
    definition_file = definition_file,
    data_file = basename(data_file_path)
  )
}

#' Format metadata for display
#'
#' @param metadata Metadata object created by create_metadata
#' @return A formatted string of metadata information
format_metadata <- function(metadata) {
  sprintf(
    "Created: %s\nRows: %d\nColumns: %d\nDefinition: %s\nData: %s",
    format(metadata$created_at),
    metadata$row_count,
    metadata$column_count,
    metadata$definition_file,
    metadata$data_file
  )
} 