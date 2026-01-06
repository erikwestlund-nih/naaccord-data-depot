from io import StringIO

import numpy as np
import pandas as pd
from django.template.loader import render_to_string
from django_sonar.utils import sonar

from depot.data import validator
from depot.data import summarizer
from depot.data.data_file_type_to_definition_map import DataFileTypeToDefinitionMap
from depot.data.utils import filter_empty_values
from depot.models import DataFileType


class Auditor:
    data_file_type = None
    data_file_label = None
    df = None
    definition = None
    validation = {}
    summary = {}
    validator = validator.Validator()
    summarizer = summarizer.Summarizer()

    def __init__(self, data_file_type: str, data_content: str):
        self.data_file_type = data_file_type
        self.data_file_type_label = DataFileType.objects.get(name=data_file_type).label
        self.definition = self.get_definition(data_file_type)
        self.df = self.process_data(
            pd.read_csv(
                StringIO(data_content),
                na_values=[],
                keep_default_na=False,
                low_memory=False,
            ),
            self.definition.definition,
        )[0]

    def get_definition(self, name):
        definition = DataFileTypeToDefinitionMap().get(name)

        return definition()  # Instantiate

    def process_data(self, df, definition):
        logs = {}
        for var_definition in definition:
            column = var_definition["name"]
            type = var_definition["type"]

            if column not in df:
                logs[column] = f"Column '{column}' not found in data."
                continue

            try:
                if type == "id":
                    # Ensure IDs are strings (light coercion for mixed types)
                    df[column] = df[column].astype(str)
                    logs[column] = "Coerced to string (ID)."

                elif type == "string":
                    # Ensure strings are strings (light coercion for mixed types)
                    df[column] = df[column].astype(str)
                    logs[column] = "Coerced to string."

                elif type in ["number", "float"]:
                    # Convert to numeric (allows float, int, NaN)
                    df[column] = pd.to_numeric(df[column], errors="coerce")
                    logs[column] = "Coerced to numeric (float)."

                elif type == "int":
                    # Convert to integers, with NaN for invalid values
                    df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                        "Int64"
                    )
                    logs[column] = "Coerced to integer."

                elif type == "year":
                    # Convert to integer (valid years only, e.g., between 0 and 9999)
                    df[column] = pd.to_numeric(df[column], errors="coerce").astype(
                        "Int64"
                    )
                    df[column] = df[column].where(
                        (df[column] >= 0) & (df[column] <= 9999)
                    )
                    logs[column] = "Coerced to integer year (0–9999)."

                elif type == "enum":
                    # Convert to category (useful for enum-like values)
                    df[column] = df[column].astype("category")
                    categories = df[column].cat.categories
                    updated_categories = categories.map(
                        lambda x: pd.NA if x == "" else x
                    )
                    df[column] = df[column].cat.rename_categories(updated_categories)
                    logs[column] = "Coerced to category (enum)."

                elif type == "date":
                    # Convert to a string; it will be validated as a data in the correct format later.
                    df[column] = df[column].astype(str)
                    logs[column] = "Datetime oerced to string for processing."

                else:
                    logs[column] = f"Unknown type '{type}', no action taken."

            except Exception as e:
                logs[column] = f"Error during coercion: {str(e)}"

        return df, logs

    def handle(self):
        self.validation = self.validator.handle(self.definition, self.df)
        self.summary = self.summarizer.handle(self.definition, self.df)

        return {
            "data_file_type": self.data_file_type,
            "data_file_type_label": self.data_file_type_label,
            "df": self.df,
            "variable_count": self.df.shape[1],
            "record_count": self.df.shape[0],
            "net_empty_pct": self.get_net_empty_pct(),  # Total missing values / total values
            "validation": self.validation,
            "summary": self.summary,
        }

    def get_net_empty_pct(self):
        data = filter_empty_values(self.df)
        missing = data.isnull().sum().sum()
        total = data.size

        return round(100 * missing / total, 1)
