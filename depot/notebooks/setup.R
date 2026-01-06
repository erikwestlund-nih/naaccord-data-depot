# Source the scaffold file
source(here::here("depot", "scaffold_r.R"))

# Load NAATools package
load_naatools()

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

# Load depot R files
load_depot_r()

# Load notebook functions
load_notebook_functions()
