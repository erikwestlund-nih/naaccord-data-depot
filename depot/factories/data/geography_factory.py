from datetime import datetime
from typing import Dict, Union, Callable, List
from depot.factories.data.base_factory import BaseFactory, fake


class GeographyFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "stateProv": lambda: fake.random_element(
                [
                    "WA",
                    "CA",
                    "NY",
                    "TX",
                    "FL",
                    "ON",
                    "BC",
                    "QC",
                    "AB",
                    "NU",
                    "XX",
                ]  # US states and Canadian provinces, 'XX' if unknown
            ),
            "postCode": lambda: fake.random_element(
                [
                    fake.zipcode(),  # US ZIP Code
                    fake.postcode(),  # Canadian Postal Code
                    "ZZZ",  # Homeless (no known shelter ZIP)
                ]
            ),
            "resDate": lambda: fake.date_between(start_date="-30y", end_date="today"),
            "stateProvApprox": lambda: fake.boolean(
                chance_of_getting_true=20
            ),  # 20% chance it's approximated
        }
