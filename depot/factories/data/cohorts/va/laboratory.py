import random
from depot.factories.data.laboratory_factory import LaboratoryFactory


class VaLaboratoryFactory(LaboratoryFactory):
    # Partner-specific overrides
    predefined_rows = [
        {
            "result": "50",
            "result_type": "numeric",
            "testName": "HIV-1 Viral Load Assay (Unspecified)",
            "source": "L4",
            "interpretation": "LT",
            "normalMin": "50",
            "units": "copies/mL",
            "file": 3,
            "n": 163952,
            "meta": {"freq": 0.05},  # 5% probability of using this row
        },
        {
            "result": "Not D",
            "result_type": "character",
            "testName": "SARS-CoV-2 (COVID-19) PCR Qualitative",
            "source": "L4",
            "interpretation": "NA",
            "normalMin": "NA",
            "units": "NA",
            "file": 3,
            "n": 127511,
            "meta": {"freq": 0.02},  # 2% probability
        },
        {
            "result": lambda: str(random.uniform(0.5, 1.5)),  # Random value in range
            "result_type": "numeric",
            "testName": "Creatinine",
            "source": "L4",
            "interpretation": "NA",
            "normalMin": "NA",
            "units": "mg/dL",
            "file": 2,
            "n": 100000,
            "meta": {"freq": 0.15},  # 15% probability
        },
    ]

    def create(self, num_records: int, custom_generators=None):
        """Generate records, incorporating predefined rows & error injection."""
        field_generators = {**self.field_generators, **(custom_generators or {})}

        data = []
        for _ in range(num_records):
            record = {}

            # Step 1: Select a predefined row (based on freq) or generate new
            total_freq = sum(row["freq"] for row in self.predefined_rows)
            if random.random() < total_freq:
                row = random.choices(
                    self.predefined_rows,
                    weights=[r["freq"] for r in self.predefined_rows],
                )[0]
                record = {
                    k: (v() if callable(v) else v) for k, v in row["values"].items()
                }
            else:
                for field, generator_or_default in field_generators.items():
                    record[field] = (
                        generator_or_default()
                        if callable(generator_or_default)
                        else generator_or_default
                    )

            # Step 2: Apply column name mapping (renaming)
            record = {
                self.meta["column_mapping"].get(k, k): v for k, v in record.items()
            }

            # Step 3: Apply error injection
            for field, rules in self.meta["error_injection"].items():
                if "null_prob" in rules and random.random() < rules["null_prob"]:
                    record[field] = None
                if (
                    "duplicate_prob" in rules
                    and random.random() < rules["duplicate_prob"]
                ):
                    record["cohortPatientId"] = record[
                        "cohortPatientId"
                    ]  # Duplicate ID

            data.append(record)

        self.data = data
        return self
