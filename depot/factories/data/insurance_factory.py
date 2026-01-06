from datetime import datetime
from typing import Dict, Union, Callable, List
from depot.factories.data.base_factory import BaseFactory, fake


class InsuranceFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "insurance": lambda: fake.random_element(
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"]
            ),
            "insuranceStartDate": lambda: fake.date_between(
                start_date="-30y", end_date="today"
            ),
            "insuranceStopDate": lambda: (
                fake.date_between(start_date="-20y", end_date="today")
                if fake.boolean(70)
                else None
            ),
        }
