import os
import importlib
from django.core.management.base import BaseCommand
from depot import settings
from depot.factories.data.patient_factory import PatientFactory
from depot.factories.data.diagnosis_factory import DiagnosisFactory
from depot.factories.data.laboratory_factory import LaboratoryFactory
from depot.factories.data.medication_factory import MedicationFactory
from depot.factories.data.mortality_factory import MortalityFactory
from depot.factories.data.geography_factory import GeographyFactory
from depot.factories.data.encounter_factory import EncounterFactory
from depot.factories.data.insurance_factory import InsuranceFactory
from depot.factories.data.hospitalization_factory import HospitalizationFactory
from depot.factories.data.substance_survey_factory import SubstanceSurveyFactory
from depot.factories.data.procedure_factory import ProcedureFactory
from depot.factories.data.discharge_diagnosis_factory import DischargeDiagnosisFactory
from depot.factories.data.risk_factor_factory import RiskFactorFactory
from depot.factories.data.census_factory import CensusFactory


class Command(BaseCommand):
    help = "Generate simulated data for a specified cohort and table."

    default_factories = {
        "patient": PatientFactory,
        "diagnosis": DiagnosisFactory,
        "laboratory": LaboratoryFactory,
        "medication": MedicationFactory,
        "mortality": MortalityFactory,
        "geography": GeographyFactory,
        "encounter": EncounterFactory,
        "insurance": InsuranceFactory,
        "hospitalization": HospitalizationFactory,
        "substance_survey": SubstanceSurveyFactory,
        "procedure": ProcedureFactory,
        "discharge_dx": DischargeDiagnosisFactory,
        "risk_factor": RiskFactorFactory,
        "census": CensusFactory,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--cohort",
            type=str,
            required=True,
            help="Specify the cohort name (e.g., 'va').",
        )
        parser.add_argument(
            "--table",
            type=str,
            choices=self.default_factories.keys(),
            required=True,
            help="Specify the table name (e.g., 'laboratory').",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of records to generate (default: 10).",
        )

    def handle(self, *args, **kwargs):
        cohort_name = kwargs.get("cohort").lower()
        table_name = kwargs.get("table").lower()
        count = kwargs.get("count")

        factory = self.load_factory(cohort_name, table_name)
        if not factory:
            self.stderr.write(
                f"Factory for cohort '{cohort_name}' and table '{table_name}' not found."
            )
            return

        # Generate data
        records = factory.create(count)

        # Save the data
        save_dir = os.path.join(
            settings.BASE_DIR, "resources", "data", "generated", "cohorts", cohort_name
        )
        os.makedirs(save_dir, exist_ok=True)  # Ensure directory exists
        self.save(records, save_dir, f"{table_name}.csv")

        self.stdout.write(
            f"Generated {count} records for cohort '{cohort_name}' and table '{table_name}', saved to {save_dir}"
        )

    def load_factory(self, cohort, table):
        """
        Attempts to load a cohort-specific factory. Falls back to the default factory.
        """
        module_path = f"depot.factories.data.cohorts.{cohort}.{table}"
        try:
            module = importlib.import_module(module_path)
            return getattr(
                module, f"{cohort.capitalize()}{table.capitalize()}Factory"
            )()
        except (ModuleNotFoundError, AttributeError):
            self.stdout.write(
                f"No cohort-specific factory found for {cohort}.{table}, using default factory."
            )
            return self.default_factories.get(table)()

    def save(self, data, save_dir, filename):
        data.save_csv(save_dir, filename)
