library(here)
library(duckdb)
library(dplyr)
library(knitr)
library(kableExtra)
library(jsonlite)

notebook_includes <- c(
  "util.R",
  "definitions.R",
  "validation.R"
)

for (include in notebook_includes) {
  source(here("depot", "notebooks", "functions", include))
}

r_includes <- c(
  "util.R",
  "definitions.R",
  "validation.R"
)

for (include in r_includes) {
  source(here("depot", "R", include))
}
