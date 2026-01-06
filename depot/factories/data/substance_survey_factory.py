from datetime import datetime
from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class SubstanceSurveyFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "question": lambda: fake.random_element(
                ["smoke1", "drinksday", "druguse", "alcoholfreq", "caffeine"]
            ),
            "response": lambda: fake.random_element(
                ["Yes", "No", "1-3", "4-6", "Daily", "Occasionally", "Never"]
            ),
            "responseDate": lambda: fake.date_between(
                start_date="-20y", end_date="today"
            ),
            "questionLabel": lambda: fake.random_element(
                [
                    "Have you ever smoked?",
                    "How many drinks per day?",
                    "Have you used illicit drugs?",
                    "How often do you consume alcohol?",
                    "How much caffeine do you consume daily?",
                ]
            ),
            "responseLabel": lambda: fake.random_element(
                ["Never", "Occasionally", "Regularly", "Heavy use", "Light use"]
            ),
        }
