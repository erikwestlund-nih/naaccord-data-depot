def summarize(definition, df):
    return {
        "name": definition["name"],
        "description": definition["description"],
        "unique_values_count": df[definition["name"]].nunique(),
        "example_values": df[definition["name"]].sample(5).tolist(),
        "missing": df[definition["name"]].isnull().sum(),
    }
