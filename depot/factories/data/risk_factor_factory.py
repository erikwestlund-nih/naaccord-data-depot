from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class RiskFactorFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "risk": lambda: fake.random_element(
                [
                    "Men who have sex with men",
                    "Injection drug use",
                    "Men who have sex with men and are an injection drug user",
                    "Hemophilia/coagulation disorder",
                    "Heterosexual contact - Unspecified",
                    "Heterosexual contact - Sex with injection drug user",
                    "Heterosexual contact - Sex with bisexual male",
                    "Heterosexual contact - Sex with person with hemophilia",
                    "Heterosexual contact - Sex with transfusion recipient with HIV infection",
                    "Heterosexual contact - Sex with HIV-infected person, risk not specified",
                    "Receipt of blood transfusion, blood components, or tissue",
                    "Worked in health care or laboratory setting",
                    "Perinatal",
                    "Other",
                    "Unknown",
                ]
            ),
        }
