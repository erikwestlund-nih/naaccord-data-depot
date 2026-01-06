from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class PatientFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": fake.uuid4,
            "birthSex": lambda: fake.random_element(["Female", "Male", "Intersexed"]),
            "presentSex": lambda: fake.random_element(["Female", "Male", "Intersexed"]),
            "birthYear": lambda: fake.random_int(
                min=1900, max=datetime.now().year - 18
            ),
            "race": lambda: fake.random_element(
                [
                    "White",
                    "Black",
                    "Asian",
                    "Pacific Islander",
                    "Native American",
                    "Multiracial",
                    "Other",
                    "Unknown",
                ]
            ),
            "hispanic": lambda: fake.random_element([1, 0]),
            "enrollDate": lambda: fake.date_between(start_date="-30y", end_date="-5y"),
            "lastActivityDate": lambda: fake.date_between(
                start_date="-5y", end_date="today"
            ),
            "deathDate": lambda: (
                fake.date_between(start_date="-5y", end_date="today")
                if fake.boolean(chance_of_getting_true=30)
                else None
            ),
            "deathDateSource": lambda: fake.random_element(["Clinic reported", "SSDI"]),
            "subSiteID": lambda: str(fake.random_int(min=1, max=100, step=1)),
            "hivNegative": lambda: fake.random_element(["Y", "S"]),
            "BirthCountry": lambda: fake.random_element(["US", fake.country()]),
            "transgendered": lambda: fake.random_element(["Yes", "No"]),
            "LastNDIDate": lambda: fake.date_between(
                start_date="-10y", end_date="today"
            ),
        }
