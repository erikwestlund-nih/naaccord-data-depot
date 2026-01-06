render_summary <- function(summary_result, db_stats) {
  # Check for empty or invalid summary results
  if (is.null(summary_result) || length(summary_result) == 0) {
    cat("No summary data available.\n\n")
    return()
  }

  # Group results by summarizer type
  grouped_results <- split(summary_result, sapply(summary_result, function(x) x$summarizer))
  
  # Handle each type of summary separately
  for (summarizer_type in names(grouped_results)) {
    results <- grouped_results[[summarizer_type]]
    if (length(results) == 0) next
    
    # Create appropriate heading
    cat(sprintf("\n##### %s\n\n", format_summarizer_name(summarizer_type)))
    
    # Add description based on summarizer type
    switch(summarizer_type,
      "basic_stats" = cat("<span style='font-size: 0.9em; color: #666;'>Overview of the variable's basic characteristics including counts and uniqueness.</span>\n\n"),
      "string" = cat(""),
      "examples" = cat("<span style='font-size: 0.9em; color: #666;'>The most common values found in the data.</span>\n\n"),
      "numeric_coercion" = cat("<span style='font-size: 0.9em; color: #666;'>Analysis of whether string values can be converted to numbers.</span>\n\n"),
      "barchart" = cat("<span style='font-size: 0.9em; color: #666;'>Visual representation of the most frequent values.</span>\n\n"),
      "histogram" = cat("<span style='font-size: 0.9em; color: #666;'>Distribution of numeric values.</span>\n\n"),
      "date" = cat("<span style='font-size: 0.9em; color: #666;'>Analysis of date ranges and distribution in the data.</span>\n\n")
    )
    
    # Handle each type of summary differently
    switch(summarizer_type,
      "basic_stats" = {
        # Create a table for basic stats
        stats <- results[[1]]$value
        if (!is.null(stats) && all(!sapply(stats, is.null))) {
          stats_df <- data.frame(
            Metric = c("Count", "Unique", "Empty"),
            Value = c(
              format(stats$count, big.mark=","),
              format(stats$unique, big.mark=","),
              sprintf("%s (%s)", format(stats$empty, big.mark=","), stats$empty_pct)
            ),
            stringsAsFactors = FALSE
          )
          print(kable(stats_df, 
              row.names = FALSE,
              format = "html",
              escape = FALSE) |>
            kable_styling(bootstrap_options = c("hover")) |>
            column_spec(2, monospace = TRUE, width = "250px"))
        }
      },
      
      "date" = {
        # Create a table for date stats
        stats <- results[[1]]$value$date_stats
        if (!is.null(stats) && all(!sapply(stats, is.null))) {
          # Basic date stats
          stats_df <- data.frame(
            Metric = c("Total Count", "Date Range", "Bin Size", "Number of Bins"),
            Value = c(
              stats$total,
              sprintf("%s to %s", stats$min_date, stats$max_date),
              stats$bin_size,
              as.character(stats$n_bins)
            ),
            stringsAsFactors = FALSE
          )
          print(kable(stats_df, 
              row.names = FALSE,
              format = "html",
              escape = FALSE) |>
            kable_styling(bootstrap_options = c("hover")) |>
            column_spec(2, monospace = TRUE, width = "150px"))
          
          # Display histogram directly
          if (!is.null(results[[1]]$value$histogram)) {
            cat("\n**Date Distribution:**\n\n")
            print(results[[1]]$value$histogram)
          }
        }
      },
      
      "string" = {
        # Create a table for string stats
        stats <- results[[1]]$value
        if (!is.null(stats)) {
          # Length stats
          if (!is.null(stats$length_stats) && all(!sapply(stats$length_stats, is.null))) {
            cat("**Length Statistics:**\n\n")
            cat("<span style='font-size: 0.9em; color: #666;'>Number of characters in each value.</span>\n\n")
            length_df <- data.frame(
              Metric = c("Minimum", "Maximum", "Average"),
              Value = c(
                stats$length_stats$min,
                stats$length_stats$max,
                stats$length_stats$avg
              ),
              stringsAsFactors = FALSE
            )
            print(kable(length_df, 
                row.names = FALSE,
                format = "html",
                escape = FALSE) |>
              kable_styling(bootstrap_options = c("hover")) |>
              column_spec(2, monospace = TRUE, width = "100px"))
          }
          
          # Pattern stats
          if (!is.null(stats$pattern_stats) && all(!sapply(stats$pattern_stats, is.null))) {
            cat("\n\n<br>\n\n")
            cat("\n**Pattern Statistics:**\n\n")
            cat("<span style='font-size: 0.9em; color: #666;'>Distribution of character types (letters, numbers, mixed) in the values. 'Other' contains symbols.</span>\n\n")
            pattern_df <- data.frame(
              Pattern = c("Letters only", "Numbers only", "Letters and numbers", "Other"),
              Count = c(
                format(stats$pattern_stats$letters_only, big.mark=","),
                format(stats$pattern_stats$numbers_only, big.mark=","),
                format(stats$pattern_stats$letters_and_numbers, big.mark=","),
                format(stats$pattern_stats$other, big.mark=",")
              ),
              stringsAsFactors = FALSE
            )
            print(kable(pattern_df, 
                row.names = FALSE,
                format = "html",
                escape = FALSE) |>
              kable_styling(bootstrap_options = c("hover")) |>
              column_spec(2, monospace = TRUE, width = "100px"))
          }
        }
      },
      
      "length" = {
        # Create a table for length stats
        stats <- results[[1]]$value
        if (!is.null(stats)) {
          if (!is.null(stats$length_stats) && all(!sapply(stats$length_stats, is.null))) {
            length_df <- data.frame(
              Metric = c("Minimum", "Maximum", "Average"),
              Value = c(
                stats$length_stats$min,
                stats$length_stats$max,
                stats$length_stats$avg
              ),
              stringsAsFactors = FALSE
            )
            print(kable(length_df, 
                row.names = FALSE,
                format = "html",
                escape = FALSE) |>
              kable_styling(bootstrap_options = c("hover")) |>
              column_spec(2, monospace = TRUE, width = "100px"))
          }
          
          # Most common lengths
          if (!is.null(stats$common_lengths) && is.data.frame(stats$common_lengths) && nrow(stats$common_lengths) > 0) {
            cat("\n**Most Common Lengths:**\n\n")
            common_df <- data.frame(
              Length = stats$common_lengths$length,
              Count = format(stats$common_lengths$count, big.mark=","),
              Percentage = stats$common_lengths$pct,
              stringsAsFactors = FALSE
            )
            print(kable(common_df, 
                row.names = FALSE,
                format = "html",
                escape = FALSE) |>
              kable_styling(bootstrap_options = c("hover")) |>
              column_spec(2:3, monospace = TRUE, width = "100px"))
          }
        }
      },
      
      "examples" = {
        # Create a table for examples
        examples <- results[[1]]$value$examples
        if (!is.null(examples) && is.data.frame(examples) && nrow(examples) > 0) {
          examples_df <- data.frame(
            Value = examples$value,
            Count = format(examples$count, big.mark=","),
            Percentage = examples$pct,
            stringsAsFactors = FALSE
          )
          print(kable(examples_df, 
              row.names = FALSE,
              format = "html",
              escape = FALSE,
              align = c('l', 'r', 'r')) |>  # Specify alignment for each column
            kable_styling(bootstrap_options = c("hover")) |>
            column_spec(1, width = "200px") |>  # Left column gets more width
            column_spec(2:3, monospace = TRUE, width = "100px"))  # Numeric columns
        }
      },
      
      "numeric_coercion" = {
        # Create a table for numeric coercion stats
        stats <- results[[1]]$value$coercion_stats
        if (!is.null(stats) && all(!sapply(stats, is.null))) {
          coercion_df <- data.frame(
            Category = c("Numeric", "Cannot coerce to number"),
            Count = c(
              format(stats$can_coerce, big.mark=","),
              format(stats$cannot_coerce, big.mark=",")
            ),
            stringsAsFactors = FALSE
          )
          print(kable(coercion_df, 
              row.names = FALSE,
              format = "html",
              escape = FALSE) |>
            kable_styling(bootstrap_options = c("hover")) |>
            column_spec(2, monospace = TRUE, width = "100px"))
        }
      },
      
      "barchart" = {
        # For barchart, use the ggplot object directly
        if (!is.null(results[[1]]$value)) {
          plot_obj <- results[[1]]$value
          if (inherits(plot_obj, "ggplot")) {
            print(plot_obj)
          }
        }
      },
      
      "histogram" = {
        # For histogram, use the ggplot object directly
        if (!is.null(results[[1]]$value)) {
          plot_obj <- results[[1]]$value
          if (inherits(plot_obj, "ggplot")) {
            print(plot_obj)
          }
        }
      },
      
      # Default case for any other types
      {
        for (result in results) {
          if (!is.null(result$value_rendered)) {
            plot_obj <- result$value_rendered$data
            if (inherits(plot_obj, "plotly")) {
              knitr::knit_print(plot_obj)
            } else if (inherits(plot_obj, "ggplot")) {
              p <- ggplotly(plot_obj)
              knitr::knit_print(p)
            }
          } else if (!is.null(result$value)) {
            cat(as.character(result$value), "\n\n")
          } else {
            cat(result$message, "\n\n")
          }
        }
      }
    )
    
    cat("\n\n<br>\n\n")
  }
  
}

# Helper function to format summarizer names
format_summarizer_name <- function(name) {
  # Convert snake_case to Title Case
  name <- gsub("_", " ", name)
  name <- tools::toTitleCase(name)
  return(name)
}

summarize_submitted_file <- function(duckdb_file_path, var, definition) {
  # Open DuckDB connection
  duckdb_conn <- NAATools::open_duckdb_connection(duckdb_file_path)
  on.exit(NAATools::close_duckdb_connection(duckdb_conn))

  # Check if variable exists in the data
  if (!NAATools::column_exists(duckdb_conn, "data", var)) {
    # Return a single summary result indicating missing column
    return(list(
      NAATools::format_summary_result(
        summarizer = "column_exists",
        status = "error",
        message = sprintf("Column '%s' is defined in the table definition but not found in the submitted data", var),
        value = NULL
      )
    ))
  }

  # Get all summarizers for this variable
  summarizers <- get_var_summarizers(definition)

  # Run each summarizer and collect results
  results <- lapply(summarizers, function(summarizer) {
    # Construct the summarizer function name
    summarizer_fn_name <- paste0("summarize_", summarizer$name)

    # Get the summarizer function from NAATools
    summarizer_fn <- get(summarizer_fn_name, envir = asNamespace("NAATools"))

    # Call the summarizer function
    summary_results <- summarizer_fn(
      duckdb_conn = duckdb_conn,
      table_name = "data",
      var = var,
      params = summarizer$params
    )

    # Format the result using NAATools function
    NAATools::format_summary_result(
      summarizer = summarizer$name,
      status = summary_results$status,
      message = summary_results$message,
      value = summary_results$value
    )
  })

  # Return all summary results
  results
}

get_var_summarizers <- function(var_definition) {
  # Check if there's a visualize field (used in patient_definition)
  # and convert it to summarizers
  if (!is.null(var_definition$visualize)) {
    # Map visualize names to summarizer names
    visualize_summarizers <- lapply(var_definition$visualize, function(viz) {
      summarizer_name <- if (viz == "histogram") "histogram" else viz
      list(name = summarizer_name, params = NULL)
    })
  } else {
    visualize_summarizers <- list()
  }
  
  # Check if there are explicit summarizers
  if (!is.null(var_definition$summarizers)) {
    explicit_summarizers <- lapply(var_definition$summarizers, function(summarizer) {
      if (is.character(summarizer)) {
        # Convert bar_chart to barchart for consistency
        summarizer_name <- if (summarizer == "bar_chart") "barchart" else summarizer
        list(name = summarizer_name, params = NULL)
      } else {
        summarizer
      }
    })
  } else {
    explicit_summarizers <- list()
  }
  
  # Get the type-specific summarizers
  type_summarizers <- switch(var_definition$type,
    "string" = list(
      list(name = "string", params = NULL),
      list(name = "examples", params = NULL),
      list(name = "numeric_coercion", params = NULL),
      list(name = "barchart", params = NULL)
    ),
    "number" = list(
      list(name = "number", params = NULL),
      list(name = "histogram", params = NULL)
    ),
    "numeric" = list(
      list(name = "number", params = NULL),
      list(name = "histogram", params = NULL)
    ),
    "integer" = list(
      list(name = "number", params = NULL),
      list(name = "histogram", params = NULL)
    ),
    "year" = list(
      list(name = "number", params = NULL),
      list(name = "histogram", params = NULL)
    ),
    "date" = list(
      list(name = "date", params = NULL)
    ),
    "boolean" = list(
      list(name = "examples", params = NULL),
      list(name = "barchart", params = NULL)
    ),
    "enum" = list(
      list(name = "examples", params = NULL),
      list(name = "barchart", params = NULL)
    ),
    "id" = list(
      list(name = "examples", params = NULL)
    ),
    list()  # Default case
  )
  
  # Combine all summarizers, prioritizing explicit/visualize over type defaults
  # Remove duplicates by name
  all_summarizers <- c(
    list(list(name = "basic_stats", params = NULL)),  # Universal summarizer
    explicit_summarizers,
    visualize_summarizers,
    type_summarizers
  )
  
  # Remove duplicates by summarizer name
  seen_names <- character()
  unique_summarizers <- list()
  for (summarizer in all_summarizers) {
    if (!(summarizer$name %in% seen_names)) {
      unique_summarizers <- c(unique_summarizers, list(summarizer))
      seen_names <- c(seen_names, summarizer$name)
    }
  }
  
  unique_summarizers
}
