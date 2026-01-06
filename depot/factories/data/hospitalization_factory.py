from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class HospitalizationFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "encounterID": lambda: fake.uuid4(),
            "admitDate": lambda: fake.date_between(start_date="-30y", end_date="today"),
            "dischargeDate": lambda: (
                fake.date_between(start_date="-30y", end_date="today")
                if fake.boolean(chance_of_getting_true=90)
                else None  # Some records may not have a discharge date yet
            ),
        }
