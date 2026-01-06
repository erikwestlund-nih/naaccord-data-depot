# Validator Reference

**Complete reference for all data validation rules in NA-ACCORD**

Validators ensure data quality by checking that submitted values meet the research protocol requirements. Each validator can be configured with specific parameters to control its behavior.

## Overview

Validators are applied to variables defined in JSON data definitions. They check data against rules like type constraints, required values, allowed enumerations, and conditional logic.

## Validator Types

### Boolean

**Purpose**: Ensures a value matches allowed boolean options.

**Parameters**:
- `True`, `False`, and `Unknown`: Dictates what values are permissible for these states.

**Example**:
```python
{
    "type": "boolean",
    "allowed_values": {True: ["Yes"], False: ["No"], "Unknown": ["Unknown"]},
    "validators": [
        {"name": "boolean_allowed_values", "params": null}
    ]
}
```

---

### Date

**Purpose**: Validates that a value is a valid date in the provided format.

**Parameters**:
- `pd_date_format`: Pandas-compatible date format (e.g., `%Y-%m-%d`).
- `date_format`: Alternative format (defaults to `YYYY-MM-DD`).

**Example**:
```python
{
    "type": "date",
    "pd_date_format": "%Y-%m-%d",
    "date_format": "YYYY-MM-DD",
    "validators": [
        {"name": "date", "params": {"pd_date_format": "%Y-%m-%d", "date_format": "YYYY-MM-DD"}}
    ]
}
```

---

### Enum

**Purpose**: Ensures a value is one of the enumerated allowed options.

**Parameters**:
- `allowed_values`: List of permissible values (with optional descriptions).

**Example**:
```python
{
    "type": "enum",
    "allowed_values": ["Female", "Male", "Intersexed"],
    "validators": [
        {"name": "enum_allowed_values", "params": ["Female", "Male", "Intersexed"]}
    ]
}
```

---

### Float

**Purpose**: Validates that a value can be cast to a float.

**Parameters**: None.

**Example**:
```python
{
    "type": "float",
    "validators": [
        {"name": "float", "params": null}
    ]
}
```

---

### Forbidden When

**Purpose**: Ensures a value is forbidden under specific conditions.

**Parameters**:
- `absent`: Value is forbidden when another variable is absent.
- `present`: Value is forbidden when another variable is present.

**Example**:
```python
{
    "validators": [
        {"name": "forbidden_when", "params": {"present": "presentSex"}}
    ]
}
```

---

### Integer

**Purpose**: Ensures a value can be cast to an integer.

**Parameters**: None.

**Example**:
```python
{
    "type": "int",
    "validators": [
        {"name": "int", "params": null}
    ]
}
```

---

### No Duplicates

**Purpose**: Checks that no duplicate values exist in the dataset column.

**Parameters**: None.

**Example**:
```python
{
    "validators": [
        {"name": "no_duplicates", "params": null}
    ]
}
```

---

### Range

**Purpose**: Validates that a value falls within a specific range.

**Parameters**:
- A tuple `(min, max)` defining the range.

**Example**:
```python
{
    "type": "year",
    "validators": [
        {"name": "range", "params": [1900, 2021]}
    ]
}
```

---

### Required

**Purpose**: Ensures a value is present unless explicitly optional.

**Parameters**:
- `optional_when`: Makes the value optional under specific conditions.

**Example**:
```python
{
    "validators": [
        {"name": "required", "params": {"optional_when": "subSiteID"}}
    ]
}
```

---

### Required When

**Purpose**: Ensures a value is required under specific conditions.

**Parameters**:
- `absent`: Value is required when another variable is absent.
- `present`: Value is required when another variable is present.

**Example**:
```python
{
    "validators": [
        {"name": "required_when", "params": {"absent": "birthSex"}}
    ]
}
```

---

### String

**Purpose**: Validates that a value can be cast to a string.

**Parameters**: None.

**Example**:
```python
{
    "type": "string",
    "validators": [
        {"name": "string", "params": null}
    ]
}
```

---

### Year

**Purpose**: Ensures a value is a valid year in the range `1000–9999`.

**Parameters**: None.

**Example**:
```python
{
    "type": "year",
    "validators": [
        {"name": "year", "params": null}
    ]
}
```

## Usage

Validators are defined in JSON data definition files located in `depot/data/definitions/`. Each variable in a definition can have multiple validators applied:

```json
{
  "name": "birthYear",
  "type": "year",
  "validators": [
    {"name": "required", "params": true},
    {"name": "range", "params": [1900, 2025]}
  ]
}
```

## Related Documentation

- **[Summarizers Reference](summarizers.md)** - Data summarization and visualization
- **[Data Definitions](../technical/data-definitions.md)** - Creating data definitions
- **[NAATools Package](../naatools-dev-mode.md)** - R package for validation
