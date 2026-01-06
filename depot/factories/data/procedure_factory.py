from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class ProcedureFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "siteProcedure": lambda: fake.random_element(
                ["99213", "93000", "90791", "12001", "43239", "G0101", "A0427"]
            ),
            "procedureDate": lambda: fake.date_between(
                start_date="-30y", end_date="today"
            ),
            "procedureResult": lambda: fake.random_element(
                ["3.9", "3.9 KPa", "Normal", "Abnormal", "No significant findings"]
            ),
            "source": lambda: fake.random_element(["P1", "P2", "P3", "P4"]),
        }
