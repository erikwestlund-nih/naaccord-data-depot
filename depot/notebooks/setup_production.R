# Production setup for Quarto notebooks
# This file is self-contained and doesn't rely on here::here()

# Setup debug logging to file
debug_log_file <- file.path(tempdir(), "setup_production_debug.log")
cat(sprintf("=== Setup Production Debug Log ===\n"), file = debug_log_file, append = FALSE)
cat(sprintf("Timestamp: %s\n", Sys.time()), file = debug_log_file, append = TRUE)
cat(sprintf("Working directory: %s\n", getwd()), file = debug_log_file, append = TRUE)

# Load NAATools package (production mode only - no dev mode support)
cat("Loading NAATools package...\n", file = debug_log_file, append = TRUE)
message("Loading NAATools package...")
if (!requireNamespace("NAATools", quietly = TRUE)) {
  stop("NAATools package not found. Please install it first.")
}
library(NAATools)
cat("NAATools loaded successfully\n", file = debug_log_file, append = TRUE)
message("NAATools loaded successfully")

# Load required libraries
library(here)
library(duckdb)
library(dplyr)
library(rlang)
library(knitr)
library(kableExtra)
library(jsonlite)
library(plotly)
library(htmltools)
library(htmlwidgets)

# Load depot R files from relative path
# We're running from temp root, files are at depot/R/
r_dir <- file.path(getwd(), "depot", "R")
if (dir.exists(r_dir)) {
  message(sprintf("Loading depot R files from: %s", r_dir))
  r_files <- list.files(r_dir, pattern = "\\.R$", full.names = TRUE)
  for (file in r_files) {
    message(sprintf("  Sourcing: %s", basename(file)))
    source(file)
  }
  message("Depot R files loaded successfully")
} else {
  message(sprintf("depot/R directory not found at: %s", r_dir))
}

# Load notebook functions from relative path
# We're running from temp root, files are at depot/notebooks/functions/
functions_dir <- file.path(getwd(), "depot", "notebooks", "functions")
cat(sprintf("\n=== Loading Functions ===\n"), file = debug_log_file, append = TRUE)
cat(sprintf("Functions directory: %s\n", functions_dir), file = debug_log_file, append = TRUE)
cat(sprintf("Directory exists: %s\n", dir.exists(functions_dir)), file = debug_log_file, append = TRUE)

message(sprintf("Current working directory: %s", getwd()))
message(sprintf("Looking for functions at: %s", functions_dir))
message(sprintf("Functions directory exists: %s", dir.exists(functions_dir)))

if (dir.exists(functions_dir)) {
  message(sprintf("Loading notebook functions from: %s", functions_dir))
  function_files <- list.files(functions_dir, pattern = "\\.R$", full.names = TRUE)
  cat(sprintf("Found %d R files\n", length(function_files)), file = debug_log_file, append = TRUE)
  cat(sprintf("Files: %s\n", paste(basename(function_files), collapse = ", ")), file = debug_log_file, append = TRUE)

  message(sprintf("Found %d R files", length(function_files)))

  # Filter out setup files
  function_files <- function_files[!grepl("setup", basename(function_files), ignore.case = TRUE)]
  cat(sprintf("After filtering: %d R files\n", length(function_files)), file = debug_log_file, append = TRUE)
  message(sprintf("After filtering setup files: %d R files", length(function_files)))

  for (file in function_files) {
    cat(sprintf("Sourcing: %s\n", basename(file)), file = debug_log_file, append = TRUE)
    message(sprintf("  Sourcing: %s", basename(file)))
    tryCatch({
      source(file)
      cat(sprintf("  ✓ Success: %s\n", basename(file)), file = debug_log_file, append = TRUE)
      message(sprintf("    ✓ Successfully sourced %s", basename(file)))
    }, error = function(e) {
      cat(sprintf("  ✗ Error: %s - %s\n", basename(file), e$message), file = debug_log_file, append = TRUE)
      message(sprintf("    ✗ Error sourcing %s: %s", basename(file), e$message))
    })
  }

  # Verify init_audit_data function exists
  if (exists("init_audit_data")) {
    cat("✓ init_audit_data function EXISTS\n", file = debug_log_file, append = TRUE)
    message("✓ init_audit_data function is available")
  } else {
    cat("✗ WARNING: init_audit_data function NOT FOUND\n", file = debug_log_file, append = TRUE)
    message("✗ WARNING: init_audit_data function NOT found!")
  }

  message("Notebook functions loaded successfully")
} else {
  cat(sprintf("✗ Directory not found: %s\n", functions_dir), file = debug_log_file, append = TRUE)
  message(sprintf("✗ notebooks/functions directory not found at: %s", functions_dir))

  # List what's actually there
  parent_dir <- dirname(functions_dir)
  cat(sprintf("Parent directory: %s\n", parent_dir), file = debug_log_file, append = TRUE)
  if (dir.exists(parent_dir)) {
    files <- list.files(parent_dir, full.names = TRUE)
    cat(sprintf("Contents of parent: %s\n", paste(basename(files), collapse = ", ")), file = debug_log_file, append = TRUE)
  }
}

cat("\n=== Setup Complete ===\n", file = debug_log_file, append = TRUE)
cat(sprintf("Log file location: %s\n", debug_log_file), file = debug_log_file, append = TRUE)
message(sprintf("Setup complete. Debug log: %s", debug_log_file))
message("Setup complete")
