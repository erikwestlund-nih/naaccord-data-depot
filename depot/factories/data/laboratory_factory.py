from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class LaboratoryFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "testName": lambda: fake.random_element(
                [
                    "Albumin",
                    "Hemoglobin",
                    "Abs CD4",
                    "HIV-1 RNA RT-PCR Ultra",
                    "Glucose",
                    "Cholesterol",
                    "Triglycerides",
                    "BUN",
                    "Creatinine",
                    "ALT",
                    "AST",
                ]
            ),
            "result": lambda: fake.random_element(
                [
                    str(
                        fake.pyfloat(left_digits=2, right_digits=2, positive=True)
                    ),  # Numeric values
                    "<50",
                    ">75,000",
                    "BLQ",
                    "ALQ",
                    "Normal",
                    "High",
                    "Low",
                ]
            ),
            "units": lambda: fake.random_element(
                ["g/dL", "THOU/uL", "copies/mL", "mMol/L", "mg/dL", "U/L"]
            ),
            "normalMin": lambda: (
                str(fake.pyfloat(left_digits=1, right_digits=2, positive=True))
                if fake.boolean(chance_of_getting_true=80)
                else None
            ),
            "normalMax": lambda: (
                str(fake.pyfloat(left_digits=2, right_digits=2, positive=True))
                if fake.boolean(chance_of_getting_true=80)
                else None
            ),
            "interpretation": lambda: fake.random_element(
                [
                    "",
                    "Normal",
                    "High",
                    "Low",
                    "Abnormal",
                    "nadir",
                    "baseline",
                    "BLQ",
                    "ALQ",
                ]
            ),
            "resultDate": lambda: fake.date_between(
                start_date="-30y", end_date="today"
            ),
            "source": lambda: fake.random_element(["L1", "L2", "L3", "L4", "L5"]),
        }
