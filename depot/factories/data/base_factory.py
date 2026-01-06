import csv
import pandas as pd
from faker import Faker
from datetime import datetime
from typing import List, Dict, Callable, Union

fake = Faker()


class BaseFactory:
    field_generators = {}
    data = []

    def save_csv(self, dir: str, file_name: str) -> None:
        df = pd.DataFrame(self.data)
        path = f"{dir}/{file_name}"
        df.to_csv(path, index=False)
        print(f"Data saved to {path}")

    def create(
        self,
        num_records: int,
        custom_generators: Dict[str, Union[Callable, str]] = None,
    ):
        field_generators = {**self.field_generators, **(custom_generators or {})}

        data = []
        for _ in range(num_records):
            record = {}
            for field, generator_or_default in field_generators.items():
                record[field] = (
                    generator_or_default()
                    if callable(generator_or_default)
                    else generator_or_default
                )
            data.append(record)

        self.data = data

        return self
