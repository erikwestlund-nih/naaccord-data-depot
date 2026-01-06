from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class DiagnosisFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "diagnosis": lambda: fake.random_element(
                [
                    "Hypertension",
                    "Diabetes II",
                    "COPD",
                    "PCP",
                    "MAC",
                    "I21.01",  # ICD-10 example
                    "250.00",  # ICD-9 example (Diabetes Type II)
                    "J18.9",  # ICD-10 Pneumonia unspecified
                    "401.9",  # ICD-9 Hypertension
                    "B20",  # ICD-10 HIV Disease
                    "Depression",
                    "Anxiety",
                ]
            ),
            "diagnosisDate": lambda: fake.date_between(
                start_date="-30y", end_date="today"
            ),
            "source": lambda: fake.random_element(["D1", "D2", "D3", "D4", "D5"]),
        }
