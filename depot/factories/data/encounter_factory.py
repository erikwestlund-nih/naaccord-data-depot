from datetime import datetime
from typing import Dict, Union, Callable, List
from depot.factories.data.base_factory import BaseFactory, fake


class EncounterFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "encounterDate": lambda: fake.date_between(
                start_date="-20y", end_date="today"
            ),
            "encounterType": lambda: fake.random_element(
                [
                    "HIV Primary Care",
                    "Telemedicine – Video",
                    "Telemedicine – Phone",
                    "Telemedicine – Unspecified",
                    "Interview visit – in-person",
                    "Interview visit – not in-person",
                    "Interview visit – unspecified",
                ]
            ),
            "encounterInsType1": lambda: fake.random_element(
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"]
            ),
            "encounterInsType2": lambda: (
                fake.random_element(["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"])
                if fake.boolean(30)
                else ""
            ),
            "encounterInsType3": lambda: (
                fake.random_element(["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"])
                if fake.boolean(20)
                else ""
            ),
            "encounterInsType4": lambda: (
                fake.random_element(["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"])
                if fake.boolean(10)
                else ""
            ),
            "encounterInsType5": lambda: (
                fake.random_element(["1", "2", "3", "4", "5", "6", "7", "8", "9", "99"])
                if fake.boolean(5)
                else ""
            ),
        }
