import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import json
import importlib

if len(sys.argv) != 3:
    print("Usage: python convert_definition_to_json.py <module_path> <class_name>")
    print(
        "Example: python convert_definition_to_json.py depot.data.definitions.laboratory_definition Laboratory"
    )
    sys.exit(1)

module_path = sys.argv[1]
class_name = sys.argv[2]

# Dynamically import the module and class
module = importlib.import_module(module_path)
definition_class = getattr(module, class_name)

# Get the definition
definition = definition_class.definition

# Determine output path (same directory as module)
module_file = module.__file__
output_dir = os.path.dirname(module_file)
output_filename = f"{class_name.lower()}_definition.json"
output_path = os.path.join(output_dir, output_filename)

# Write to JSON
with open(output_path, "w") as f:
    json.dump(definition, f, indent=2)

print(f"Wrote {class_name} definition to {output_path}")
