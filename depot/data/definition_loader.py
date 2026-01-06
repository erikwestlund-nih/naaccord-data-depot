"""
Simple JSON-based definition loader for data file types.
"""
import json
from pathlib import Path


class JSONDefinition:
    """Wrapper class for JSON definitions to match the expected interface."""
    
    def __init__(self, definition_path):
        self.definition_path = Path(definition_path)
        with open(self.definition_path, 'r') as f:
            self.definition = json.load(f)
    
    def get_definition(self):
        return self.definition


def get_definition_for_type(data_file_type):
    """
    Load a JSON definition for a given data file type.
    
    Args:
        data_file_type: Name of the data file type (e.g., 'patient', 'laboratory')
    
    Returns:
        JSONDefinition instance
    """
    base_path = Path(__file__).parent / 'definitions'
    definition_file = base_path / f'{data_file_type}_definition.json'
    
    if not definition_file.exists():
        raise ValueError(f"Definition file not found for type: {data_file_type}")
    
    return JSONDefinition(definition_file)