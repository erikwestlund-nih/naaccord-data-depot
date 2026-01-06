from typing import Dict, Union, Callable, List

from depot.factories.data.base_factory import BaseFactory, fake


class CensusFactory(BaseFactory):
    def __init__(self):
        self.field_generators = {
            "cohortPatientId": lambda: fake.uuid4(),
            "resDate": lambda: fake.date_between(start_date="-30y", end_date="today"),
            "censusTract": lambda: f"{fake.random_int(min=1000, max=9999)}.{fake.random_int(min=0, max=99):02}",
            "zcta": lambda: f"{fake.random_int(min=10000, max=99999)}",
            "county": lambda: fake.city(),
            "state": lambda: fake.state(),
            "mTractIncome": lambda: fake.random_int(min=20000, max=150000),
            "mZCTAIncome": lambda: fake.random_int(min=20000, max=150000),
            "mCountyIncome": lambda: fake.random_int(min=20000, max=150000),
            "mStateIncome": lambda: fake.random_int(min=20000, max=150000),
            "pTractEmployed": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pZCTAEmployed": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pCountyEmployed": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pStateEmployed": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pTractCollege": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pZCTACollege": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pCountyCollege": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
            "pStateCollege": lambda: round(fake.pyfloat(min_value=0, max_value=1), 2),
        }
