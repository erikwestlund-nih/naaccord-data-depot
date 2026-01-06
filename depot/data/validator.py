import importlib



class Validator:
    def handle(self, data_table_definition, df):
        results = {}

        for definition in data_table_definition.definition:
            var = definition["name"]

            # Checks if a variable is required. By default, all variables in definition are required.
            required = self.check_variable_required(var, definition)

            validators = self.construct_validators(definition)

            if not required["value"] and not validators:
                results[var] = {
                    "status": "error",
                    "message": "No validators found for the variable.",
                }
                continue

            results[var] = {
                "status": "success",
                "results": [],
            }  # Initialize

            if required["value"] and var not in df.columns:
                results[var]["results"].append(
                    {
                        "name": "variable_required",
                        "status": "error",
                        "display_name": "Variable Required",
                        "report": {
                            "pass": False,
                            "message": required["message"],
                        },
                    }
                )

            if var not in df.columns:
                continue

            for validator_item in validators:
                validator_data = self.resolve(validator_item)
                validator_name = validator_data.get("name", "(unknown)")

                if validator_data["status"] == "error":
                    results[var]["results"].append(
                        {
                            "name": validator_name,
                            "status": "error",
                            "message": validator_data["message"],
                        }
                    )
                    continue

                validator = validator_data["validator"]
                params = validator_data["params"]

                results[var]["results"].append(
                    {
                        "name": validator_name,
                        "display_name": (
                            validator.display_name
                            if hasattr(validator, "display_name")
                            else validator_name
                        ),
                        "report": validator.handle(var, df, params),
                    }
                )

        return results

    def get_validator(self, definition, validator_name):
        for validator in definition["validators"]:
            if validator["name"] == validator_name:
                return validator

        return None

    def construct_validators(self, definition):
        # Adds validators derived from definition to the validator list
        validators = []

        provided_validators = [
            validator if isinstance(validator, str) else validator.get("name")
            for validator in definition.get("validators", [])
        ]

        # By default, all variables are required to be present unless:
        # 1. There is a key value pair of "value_optional": True  or "value_required": False; OR
        if definition.get("value_optional", False) or not definition.get(
            "value_required", True
        ):
            validators += [{"name": "required", "params": False}]
        # 2. If no "required_when" or "required" validator is present, add the default 'required' validator.
        elif not any(
            key in provided_validators for key in ("required_when", "required")
        ):
            validators += [{"name": "required", "params": True}]

        type_validators = {
            "string": {"name": "string", "params": None},
            "number": {"name": "number", "params": None},
            "int": {"name": "int", "params": None},
            "float": {"name": "float", "params": None},
            "year": {"name": "year", "params": None},
            "enum": self.robust_enum_validator,
            "boolean": self.robust_boolean_validator,
            "date": self.robust_date_validator,
        }

        if definition["type"] in type_validators:
            validator = type_validators[definition["type"]]
            if callable(validator):
                validators += [validator(definition)]
            else:
                validators += [validator]

        # Add explicit validators
        if "validators" in definition:
            validators += [self.process_validator(v) for v in definition["validators"]]

        return validators

    def robust_enum_validator(self, d):
        if "allowed_values" not in d:
            raise ValueError(
                "Missing required key `allowed_values` for enum validator."
            )
        return {"name": "enum_allowed_values", "params": d["allowed_values"]}

    def robust_boolean_validator(self, d):
        if "allowed_values" not in d:
            raise ValueError(
                "Missing required key `allowed_values` for boolean validator."
            )
        return {"name": "boolean_allowed_values", "params": d["allowed_values"]}

    def robust_date_validator(self, d):
        try:
            return {
                "name": "date",
                "params": {
                    "pd_format": d["pd_date_format"],
                    "date_format": d.get("date_format", None),
                },
            }
        except KeyError as e:
            missing_key = e.args[0]
            raise ValueError(
                f"Missing required key `{missing_key}` for date validator. Input: {d}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error in date validator. Input: {d}. Details: {e}"
            ) from e

    def check_variable_required(self, var, definition):
        variable_optional_flag = definition.get("variable_optional", False)
        variable_required_flag = definition.get("variable_required", True)
        variable_optional = variable_optional_flag or not variable_required_flag

        required = False if variable_optional else True
        return {
            "value": required,
            "message": (
                f"Variable `{var}` is required."
                if required
                else f"Variable `{var}` is optional."
            ),
        }

    def process_validator(self, validator):

        if isinstance(validator, str):
            validator = {
                "name": validator,
                "params": None,
            }

        return validator

    def resolve(self, validator):

        # If just a string, convert to a dictionary
        if isinstance(validator, str):
            validator = {
                "name": validator,
                "params": None,
            }

        if "name" not in validator:
            return {
                "status": "error",
                "message": "Validator name not found.",
            }

        if "params" not in validator:
            return {
                "status": "error",
                "name": validator["name"],
                "message": "Validator params not found.",
            }

        try:
            module = importlib.import_module(
                f"depot.data.validators.{validator['name']}"
            )
            params = validator["params"]
        except ImportError:
            return {
                "status": "error",
                "name": validator["name"],
                "message": f"Validator `{validator['name']}` not found.",
            }

        return {
            "status": "success",
            "name": validator["name"],
            "validator": getattr(module, "Validator")(),
            "params": params,
        }

    def get_required_variables(self, data_table_definition):
        return [definition["name"] for definition in data_table_definition.definition]
