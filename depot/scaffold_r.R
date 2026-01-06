#' Load NAATools package in development or production mode
#'
#' @return NULL
load_naatools <- function() {
  # Check for .r_dev_mode file
  dev_mode_file <- here::here(".r_dev_mode")

  if (file.exists(dev_mode_file)) {
    # Development mode
    message("Found .r_dev_mode file - loading NAATools in development mode")
    dev_mode <- suppressWarnings(readLines(dev_mode_file))
    naatools_dir <- gsub("NAATOOLS_DIR=", "", dev_mode[grep("^NAATOOLS_DIR=", dev_mode)])
    
    # Replace $HOME with actual system home directory
    naatools_dir <- sub("$HOME", Sys.getenv("HOME"), naatools_dir, fixed = TRUE)
    
    if (dir.exists(naatools_dir)) {
      message(sprintf("Loading NAATools from development directory: %s", naatools_dir))
      devtools::load_all(naatools_dir)
      message("NAATools loaded in development mode")
    } else {
      stop(sprintf("NAATools development directory not found: %s", naatools_dir))
    }
  } else {
    # Production mode
    message("No .r_dev_mode file found - loading NAATools in production mode")
    
    if (!requireNamespace("NAATools", quietly = TRUE)) {
      message("NAATools package not found - installing from GitHub")
      # Install dependencies first
      if (!requireNamespace("remotes", quietly = TRUE)) {
        message("Installing remotes package...")
        install.packages("remotes")
      }
      
      # Install NAATools from GitHub
      message("Installing NAATools from GitHub...")
      remotes::install_github("JHBiostatCenter/naaccord-r-tools", dependencies = TRUE)
      message("NAATools installed successfully")
    }
    
    # Load the package
    message("Loading NAATools package...")
    library(NAATools)
    message("NAATools loaded successfully")
  }
}

#' Load all R files from depot R directory
#'
#' @return NULL
load_depot_r <- function() {
  r_dir <- here::here("depot", "R")
  r_files <- list.files(r_dir, pattern = "\\.R$", full.names = TRUE)
  
  # Source each file
  for (file in r_files) {
    source(file)
  }
}

#' Load all R files from depot Notebook functions directory
#'
#' @return NULL
load_notebook_functions <- function() {
  functions_dir <- here::here("depot", "notebooks", "functions")
  function_files <- list.files(functions_dir, pattern = "\\.R$", full.names = TRUE)
  
  # Filter out setup.R
  function_files <- function_files[basename(function_files) != "setup.R"]
  
  # Source each file
  for (file in function_files) {
    source(file)
  }
}
