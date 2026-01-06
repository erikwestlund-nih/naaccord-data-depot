# This class is deprecated - use definition_loader.py instead
# Keeping it for backward compatibility but it's not actively used

class DataFileTypeToDefinitionMap:
    map = {
        # These would map to Python definition classes if they existed
        # Now using JSON definitions via definition_loader.py instead
        "patient": None,
        "diagnosis": None,
        "laboratory": None,
        "medication": None,
        "mortality": None,
        "geography": None,
        "encounter": None,
        "insurance": None,
        "hospitalization": None,
        "substance_survey": None,
        "procedure": None,
        "discharge_dx": None,
        "risk_factor": None,
        "census": None,
    }

    def get(self, data_file_type):
        data_definition = self.map.get(data_file_type, None)

        if not data_definition:
            raise ValueError(
                f"Data file type '{data_file_type}' not found in data definition map."
            )

        return data_definition
