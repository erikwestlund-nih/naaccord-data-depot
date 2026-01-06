from datetime import datetime
from typing import Dict, Union, Callable, List
from depot.factories.data.base_factory import BaseFactory, fake


class MortalityFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),  # Consider reusing IDs for multiple causes per patient
            "cause": lambda: fake.random_element(
                [
                    "Cardiopulmonary arrest",
                    "HCV with liver failure",
                    "Chronic alcohol abuse",
                    "HIV Infection",
                    "Pneumonia",
                    "Bacterial sepsis",
                    "Lung cancer",
                    "PCP",
                    "Upper GI Bleed",
                    "Respiratory arrest",
                ]
            ),
            "type": lambda: fake.random_element(
                [1, 2, 3, 4, 5, 6]
            ),  # Integer instead of string
            "source": lambda: fake.random_element(
                [1, 2, 3, 4, 5, 6, 9]
            ),  # Integer instead of string
        }
