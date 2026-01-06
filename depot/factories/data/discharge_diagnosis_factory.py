from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class DischargeDiagnosisFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "dischargeDx": lambda: fake.random_element(
                ["481", "518.83", "V08", "070.70", "491.21", "V46.2"]
            ),
            "dischargeDxDate": lambda: fake.date_between(
                start_date="-30y", end_date="today"
            ),
            "ranking": lambda: fake.random_int(min=1, max=30),
            "source": lambda: "Data collected at NA-ACCORD site",
            "encounterID": lambda: fake.uuid4(),
        }
