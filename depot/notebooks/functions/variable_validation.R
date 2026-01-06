render_validation <- function(validation_results, db_stats) {
  # Display validation results
  if (length(validation_results) > 0) {
    # Create a data frame for all validation results
    validation_df <- data.frame(
      `Validation Check` = character(),
      Status = character(),
      Message = character(),
      stringsAsFactors = FALSE
    )
    
    # Collect all validation results
    for (result in validation_results) {
      # Use 'valid' to determine status badge
      status_badge <- if (isTRUE(result$valid)) {
        "✅ Success"
      } else if (!is.null(result$status) && result$status == "warn") {
        "⚠️ Warning"
      } else {
        "❌ Error"
      }
      
      # Format message with invalid catalog summary if present
      message <- result$message
      if (!is.null(result$invalid_catalog) && length(result$invalid_catalog$entries) > 0) {
        # Simplify the message to remove NULL/empty distinction
        message <- gsub(" \\([0-9]+ NULL, [0-9]+ empty\\)", "", message)
        
        # Format entries summary
        entries_summary <- sapply(result$invalid_catalog$entries, function(entry) {
          # Get total count from message
          total_count <- as.numeric(gsub(".*?([0-9]+).*", "\\1", result$invalid_catalog$message))
          
          # Format the count display
          count_display <- if (entry$count < db_stats$row_count) {
            # If showing a subset of errors
            sprintf("Showing first %d affected rows", entry$count)
          } else {
            # If showing all errors
            sprintf("%d rows (100.0%%)", entry$count)
          }
          
          if (!is.null(entry$row_ranges) && entry$row_ranges != "") {
            sprintf("%s: %s\n\nRows: %s", 
                   entry$invalid_value, 
                   count_display,
                   entry$row_ranges)
          } else {
            sprintf("%s: %s", 
                   entry$invalid_value, 
                   count_display)
          }
        })
        
        # Combine message with catalog summary
        message <- paste0(
          message, "\n\n",
          paste(entries_summary, collapse = "\n")
        )
      }
      
      # Add to data frame
      validation_df <- rbind(validation_df, data.frame(
        Validator = result$validator_name,
        Status = status_badge,
        Message = message,
        stringsAsFactors = FALSE
      ))
    }
    
    # Display the validation results table
    print(kable(validation_df, 
        row.names = FALSE,
        format = "html",
        escape = FALSE) |>
      kable_styling(bootstrap_options = c("hover")) |>
      column_spec(1, monospace = TRUE, extra_css = "font-size: 0.9em;") |>
      column_spec(2, width = "100px") |>
      column_spec(3, width = "400px"))
  }
}

#' Helper to parse params for a validator
#' @param params List of validator parameters
#' @return Formatted string of parameters
#' @export
parse_validator_params <- function(params) {
  if (is.null(params)) {
    return("")
  }
  # Custom formatting for known param types
  out <- c()
  # If there's a message, skip it here (handled separately)
  for (pn in setdiff(names(params), "message")) {
    val <- params[[pn]]
    if (is.character(val) && length(val) > 1) {
      val_str <- paste0("[", paste(val, collapse = ", "), "]")
    } else if (is.list(val) && length(val) > 1) {
      val_str <- paste0("[", paste(unlist(val), collapse = ", "), "]")
    } else if (is.character(val)) {
      val_str <- paste0("\"", val, "\"")
    } else {
      val_str <- as.character(val)
    }
    out <- c(out, paste0(pn, "=", val_str))
  }
  paste(out, collapse = ", ")
}

#' Get context string for a validator (including message if present)
#' @param validator Validator object or string
#' @return Formatted context string
#' @export
get_validator_context <- function(validator) {
  if (is.character(validator)) {
    return("")
  }
  if (!is.null(validator$params)) {
    msg <- ""
    if (!is.null(validator$params$message)) {
      msg <- paste0(validator$params$message, "\n")
    }
    params_str <- parse_validator_params(validator$params)
    context <- paste0(msg, params_str)
    return(trimws(context))
  }
  return("")
}

#' Summarize all validators in a definition, including parameters
#' @param def The definition list (as returned by read_definition)
#' @return A data.frame with columns: name, type, validator, context
#' @export
summarize_validators <- function(def) {
  rows <- do.call(rbind, lapply(def, function(var) {
    v <- var$validators
    if (is.null(v)) {
      return(NULL)
    }
    if (is.character(v)) {
      data.frame(
        name = var$name,
        type = if (!is.null(var$type)) var$type else "",
        validator = v,
        context = "",
        stringsAsFactors = FALSE
      )
    } else if (is.list(v)) {
      do.call(rbind, lapply(v, function(x) {
        if (is.character(x)) {
          data.frame(
            name = var$name,
            type = if (!is.null(var$type)) var$type else "",
            validator = x,
            context = "",
            stringsAsFactors = FALSE
          )
        } else if (!is.null(x$name)) {
          data.frame(
            name = var$name,
            type = if (!is.null(var$type)) var$type else "",
            validator = x$name,
            context = get_validator_context(x),
            stringsAsFactors = FALSE
          )
        } else {
          NULL
        }
      }))
    } else {
      NULL
    }
  }))
  if (is.null(rows)) {
    return(data.frame(name = character(), type = character(), validator = character(), context = character()))
  }
  rows <- rows[!is.na(rows$validator) & rows$validator != "", ]
  rownames(rows) <- NULL
  rows
}

#' Get validators for a variable definition
#'
#' This function processes a variable definition and returns a list of validators that should be applied
#' to validate the variable. It handles type-based validators, enum validators, boolean validators,
#' explicit validators, and required field validation.
#'
#' @param var_definition list. A variable definition containing:
#'   \itemize{
#'     \item type: The data type (string, number, int, float, year, date, boolean)
#'     \item allowed_values: Optional list of allowed values for enum/boolean validation
#'     \item validators: Optional list of explicit validators to apply
#'     \item value_optional: Optional boolean indicating if the field is optional
#'     \item value_required: Optional boolean indicating if the field is required
#'     \item date_format: Optional date format string (used with date type)
#'   }
#'
#' @return A list of validators, where each validator is a list containing:
#'   \itemize{
#'     \item name: The name of the validator
#'     \item params: Optional parameters for the validator
#'   }
#' @export
get_var_validators <- function(var_definition) {
  # Initialize empty list to store validators
  validators <- list()

  # Define type-specific validators for each supported data type
  # Each validator is a list with a name and optional parameters
  type_validators <- list(
    "string" = list(name = "string", params = NULL),
    "number" = list(name = "numeric", params = NULL),  # number type uses numeric validator
    "numeric" = list(name = "numeric", params = NULL),
    "int" = list(name = "integer", params = NULL),     # int type uses integer validator
    "integer" = list(name = "integer", params = NULL),
    "float" = list(name = "numeric", params = NULL),    # float type uses numeric validator
    "year" = list(name = "year", params = NULL),
    "date" = list(name = "date", params = list(var_definition$date_format)),
    "boolean" = list(name = "boolean", params = NULL),
    "id" = list(name = "id", params = NULL)
  )

  # Add type-specific validator if the variable has a supported type
  if (var_definition$type %in% names(type_validators)) {
    validators <- c(validators, list(type_validators[[var_definition$type]]))
  }

  # Add enum validator if the variable has allowed_values defined
  # This ensures values are restricted to the specified set
  # Skip for boolean types as they have their own special validator
  if (!is.null(var_definition$allowed_values) && var_definition$type != "boolean") {
    validators <- c(validators, list(list(
      name = "enum_allowed_values",
      params = list(allowed_values = var_definition$allowed_values)
    )))
  }

  # Add boolean validator if the variable is of type boolean and has allowed_values
  # This is a special case for boolean fields that need specific value validation
  if (!is.null(var_definition$allowed_values) && var_definition$type == "boolean") {
    validators <- c(validators, list(list(
      name = "boolean_allowed_values",
      params = list(allowed_values = var_definition$allowed_values)
    )))
  }

  # Add any explicit validators specified in the variable definition
  # These can be either simple strings or complex validator objects
  if (!is.null(var_definition$validators)) {
    for (validator in var_definition$validators) {
      if (is.character(validator)) {
        # Simple string validator (no parameters)
        validators <- c(validators, list(list(
          name = validator,
          params = NULL
        )))
      } else {
        # Complex validator object (with name and parameters)
        validators <- c(validators, list(validator))
      }
    }
  }

  # Determine if the field is optional based on value_optional or value_required flags
  is_optional <- isTRUE(var_definition$value_optional) ||
    (isTRUE(!is.null(var_definition$value_required)) && !isTRUE(var_definition$value_required))

  # Check if a required validator is already present
  has_required_validator <- any(sapply(validators, function(v) v$name %in% c("required_when", "required")))

  # Add required validator if the field is not optional and doesn't already have a required validator
  if (!is_optional && !has_required_validator) {
    validators <- c(validators, list(list(
      name = "required",
      params = TRUE
    )))
  }

  validators
}

#' Validate a submitted file against a set of validators
#' @param duckdb_file_path Path to the DuckDB file
#' @param var Variable name to validate
#' @param definition Variable definition containing validation rules
#' @return List of validation results, one for each validator
#' @export
validate_submitted_file <- function(duckdb_file_path, var, definition) {
  # Open DuckDB connection
  duckdb_conn <- NAATools::open_duckdb_connection(duckdb_file_path)
  on.exit(NAATools::close_duckdb_connection(duckdb_conn))
  
  # Check if variable exists in the data
  if (!NAATools::column_exists(duckdb_conn, "data", var)) {
    # Return a single validation result indicating missing column
    return(list(
      NAATools::format_validation_result(
        validator_name = "column_exists",
        valid = FALSE,
        message = sprintf("Column '%s' is defined in the table definition but not found in the submitted data", var),
        invalid_rows = data.frame(),
        invalid_catalog = list(),
        severity = "error"
      )
    ))
  }
  
  # Get all validators for this variable
  validators <- get_var_validators(definition)
  
  # Run each validator and collect results
  results <- lapply(validators, function(validator) {
    # Construct the validator function name
    validator_fn_name <- paste0("validate_", validator$name)
    
    # Try to get the validator function from NAATools
    validator_fn <- tryCatch({
      get(validator_fn_name, envir = asNamespace("NAATools"))
    }, error = function(e) {
      # Return NULL if validator doesn't exist
      NULL
    })
    
    # Skip if validator doesn't exist
    if (is.null(validator_fn)) {
      warning(sprintf("Validator '%s' not found in NAATools, skipping", validator_fn_name))
      return(NULL)
    }
    
    # Transform params if needed for specific validators
    params <- validator$params
    if (validator$name == "range" && is.list(params) && length(params) == 2 && is.null(names(params))) {
      # Transform array params [min, max] to named list {min: min, max: max}
      params <- list(min = params[[1]], max = params[[2]])
    } else if (validator$name == "boolean_allowed_values" && is.list(params)) {
      # Extract allowed_values if wrapped
      allowed_values <- if (!is.null(params$allowed_values)) params$allowed_values else params
      
      # Transform boolean allowed_values structure
      # From: {true: ["Yes"], false: ["No"], Unknown: ["Unknown"]}
      # To: {True: ["Yes"], False: ["No"], Unknown: ["Unknown"]}
      transformed_params <- list()
      if (!is.null(allowed_values$`true`)) transformed_params$`True` <- allowed_values$`true`
      if (!is.null(allowed_values$`false`)) transformed_params$`False` <- allowed_values$`false`
      if (!is.null(allowed_values$Unknown)) transformed_params$Unknown <- allowed_values$Unknown
      params <- transformed_params
    }
    
    # Call the validator function
    validation_results <- validator_fn(
      duckdb_conn = duckdb_conn,
      table_name = "data",
      var = var,
      params = params
    )

    # Format the result using NAATools function
    NAATools::format_validation_result(
      validator_name = validator$name,
      valid = validation_results$is_valid,
      message = validation_results$message,
      invalid_rows = validation_results$invalid_rows,
      invalid_catalog = validation_results$invalid_catalog
    )
  })
  
  # Filter out NULL results (from missing validators)
  results <- results[!sapply(results, is.null)]
  
  # Return all validation results
  results
}
