# Summarizers Reference

**Complete reference for data summarization and visualization in NA-ACCORD**

Summarizers generate statistical summaries and visualizations for variables in audit reports. The system automatically applies appropriate summarizers based on variable types, but custom summarizers can be specified.

## Overview

Summarizers tell the software how to generate statistical or visual summaries of variables. Each summarizer extends the `BaseSummarizer` class and implements a `summarize` method.

### Key Properties

- **`display_name`**: The name of the summarizer displayed in reports.
- **`summarize` Method**:
  - Parameters:
    - `variable`: The name of the variable being summarized.
    - `type`: The type of the variable (e.g., numeric, categorical).
    - `data`: The dataset containing the variable.
    - `params` (optional): Additional parameters specific to the summarizer.
  - Returns: A dictionary containing the summary status and value.

## Default Summarizers

By default, the program will infer the summarizer based on the variable type. However, you can specify a custom summarizer in the variable definition.

Summarizers are applied to variables based on their type to generate meaningful summaries and visualizations. Some summarizers are applied universally to all variables, while others are specific to certain types.

### Universal Summarizers

The following summarizers are applied to all variables by default:

- `count`: Counts the number of non-missing values.
- `unique`: Calculates the number of unique values.
- `empty`: Counts the number of missing (empty) values.
- `present`: Counts the number of non-missing (present) values.
- `empty_pct`: Calculates the percentage of missing (empty) values.
- `examples`: Provides example values from the dataset.

## Type-Specific Summarizers

### ID Variables

- No additional summarizers are applied to `id` variables.

### Numeric Variables (`number`, `int`, `float`)

- `mean`: Calculates the mean (average) value.
- `median`: Calculates the median (middle) value.
- `sd`: Calculates the standard deviation.
- `min`: Finds the minimum value.
- `max`: Finds the maximum value.
- `range`: Calculates the range (difference between max and min).
- `outliers`: Identifies outliers.
- `histogram`: Creates a histogram for distribution visualization.
- `box_plot`: Creates a box plot for distribution visualization.

### Categorical Variables (`enum`)

- `mode`: Finds the most frequent value.
- `bar_chart`: Creates a bar chart for distribution visualization.

### Boolean Variables (`boolean`)

- `bar_chart`: Creates a bar chart for distribution visualization.

### Year Variables (`year`)

- `mean`: Calculates the mean (average) value.
- `median`: Calculates the median (middle) value.
- `min`: Finds the minimum value.
- `max`: Finds the maximum value.
- `date_range`: Calculates the range of years (min and max).
- `date_histogram`: Creates a histogram for year distribution visualization.

### Date Variables (`date`)

- `min`: Finds the earliest date.
- `max`: Finds the latest date.
- `date_range`: Calculates the range of dates (min and max).
- `date_histogram`: Creates a histogram for date distribution visualization.

## Summary Table

| Variable Type     | Default Summarizers                                                                |
|-------------------|------------------------------------------------------------------------------------|
| **All Variables** | `count`, `unique`, `empty`, `present`, `empty_pct`, `examples`                     |
| **ID**            | None                                                                               |
| **Numeric**       | `mean`, `median`, `sd`, `min`, `max`, `range`, `outliers`, `histogram`, `box_plot` |
| **Categorical**   | `mode`, `bar_chart`                                                                |
| **Boolean**       | `bar_chart`                                                                        |
| **Year**          | `mean`, `median`, `min`, `max`, `date_range`, `date_histogram`                     |
| **Date**          | `min`, `max`, `date_range`, `date_histogram`                                       |

## Complete Summarizer List

### Bar Chart

**Purpose**: Creates a bar chart for categorical variables.

**Example**:
```python
{
    "summarizers": ["bar_chart"]
}
```

---

### Base Summarizer

**Purpose**: Abstract class providing the base structure for all summarizers.

**Note**: This class is not used directly but extended by other summarizers.

---

### Box Plot

**Purpose**: Generates a box plot to visualize the distribution of numeric variables.

**Example**:
```python
{
    "summarizers": ["box_plot"]
}
```

---

### Count

**Purpose**: Counts the total number of non-missing values in a variable.

**Example**:
```python
{
    "summarizers": ["count"]
}
```

---

### Date Histogram

**Purpose**: Creates a histogram to visualize the distribution of date variables.

**Example**:
```python
{
    "summarizers": ["date_histogram"]
}
```

---

### Date Range

**Purpose**: Calculates the range (minimum and maximum) of date values.

**Example**:
```python
{
    "summarizers": ["date_range"]
}
```

---

### Empty

**Purpose**: Counts the number of missing (empty) values in a variable.

**Example**:
```python
{
    "summarizers": ["empty"]
}
```

---

### Empty Percentage

**Purpose**: Calculates the percentage of missing (empty) values in a variable.

**Example**:
```python
{
    "summarizers": ["empty_pct"]
}
```

---

### Examples

**Purpose**: Provides example values from the dataset for a specific variable.

**Example**:
```python
{
    "summarizers": ["examples"]
}
```

---

### Histogram

**Purpose**: Creates a histogram to visualize the distribution of numeric variables.

**Example**:
```python
{
    "summarizers": ["histogram"]
}
```

---

### ID

**Purpose**: Validates and summarizes ID-type variables.

**Example**:
```python
{
    "summarizers": ["id"]
}
```

---

### Maximum

**Purpose**: Calculates the maximum value of a numeric variable.

**Example**:
```python
{
    "summarizers": ["max"]
}
```

---

### Mean

**Purpose**: Calculates the mean (average) value of a numeric variable.

**Example**:
```python
{
    "summarizers": ["mean"]
}
```

---

### Median

**Purpose**: Calculates the median (middle) value of a numeric variable.

**Example**:
```python
{
    "summarizers": ["median"]
}
```

---

### Minimum

**Purpose**: Calculates the minimum value of a numeric variable.

**Example**:
```python
{
    "summarizers": ["min"]
}
```

---

### Mode

**Purpose**: Calculates the mode (most frequent value) of a variable.

**Example**:
```python
{
    "summarizers": ["mode"]
}
```

---

### Outliers

**Purpose**: Identifies outliers in a numeric variable.

**Example**:
```python
{
    "summarizers": ["outliers"]
}
```

---

### Present

**Purpose**: Counts the number of non-missing (present) values in a variable.

**Example**:
```python
{
    "summarizers": ["present"]
}
```

---

### Range

**Purpose**: Calculates the range (difference between maximum and minimum) of a numeric variable.

**Example**:
```python
{
    "summarizers": ["range"]
}
```

---

### Standard Deviation (SD)

**Purpose**: Calculates the standard deviation of a numeric variable.

**Example**:
```python
{
    "summarizers": ["sd"]
}
```

---

### Unique Count

**Purpose**: Calculates the number of unique values in a variable.

**Example**:
```python
{
    "summarizers": ["unique"]
}
```

## Usage Notes

1. **Integration**: Summarizers can be added to the `summarizers` field in a variable definition.
2. **Multiple Summarizers**: Multiple summarizers can be applied to a single variable.
3. **Customization**: Custom summarizers can be created by extending the `BaseSummarizer` class.

### Example Usage

```json
{
  "name": "age",
  "type": "int",
  "description": "Patient age at enrollment",
  "summarizers": ["mean", "median", "histogram", "box_plot"]
}
```

## Implementation

Summarizers are implemented in Python in `depot/data/summarizers/` and accessed by the R package NAATools for report generation.

## Related Documentation

- **[Validators Reference](validators.md)** - Data validation rules
- **[Data Definitions](../technical/data-definitions.md)** - Creating data definitions
- **[NAATools Package](../naatools-dev-mode.md)** - R package for report generation
- **[Audit System](../technical/upload-submission-workflow.md)** - How reports are generated
