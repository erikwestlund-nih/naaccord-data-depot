from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class MedicationFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "medicationName": lambda: fake.random_element(
                [
                    "Zidovudine",
                    "Indinavir",
                    "Lamivudine",
                    "Stavudine",
                    "Efavirenz",
                    "Abacavir",
                    "Didanosine",
                    "Ritonavir",
                    "Estradiol",
                    "Testosterone",
                ]
            ),
            "startDate": lambda: (
                None
                if fake.boolean(chance_of_getting_true=10)
                else fake.date_between(start_date="-30y", end_date="today")
            ),
            "stopDate": lambda: (
                None
                if fake.boolean(chance_of_getting_true=30)
                else fake.date_between(start_date="today", end_date="+10y")
            ),
            "form": lambda: (
                None
                if fake.boolean(chance_of_getting_true=50)
                else fake.random_element(
                    ["Tablet", "Capsule", "Injection", "Liquid", "Patch"]
                )
            ),
            "strength": lambda: (
                None
                if fake.boolean(chance_of_getting_true=50)
                else str(fake.random_element([150, 300, 600, 800, 1000]))
            ),
            "units": lambda: (
                None
                if fake.boolean(chance_of_getting_true=50)
                else fake.random_element(["mg", "mg/ml", "cc", "mcg", "IU"])
            ),
            "route": lambda: (
                None
                if fake.boolean(chance_of_getting_true=50)
                else fake.random_element(["po", "IM", "SQ", "IV", "by mouth"])
            ),
            "sig": lambda: (
                None
                if fake.boolean(chance_of_getting_true=50)
                else fake.random_element(
                    [
                        "1QD",
                        "1BID",
                        "2BID",
                        "TID",
                        "Q8H",
                        "Take 1 pill daily",
                        "Take 2 pills twice a day",
                    ]
                )
            ),
            "source": lambda: fake.random_element(["M1", "M2", "M3", "M4", "M5"]),
        }
