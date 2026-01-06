import pandas as pd
import numpy as np


def filter_empty_values(data):
    if isinstance(data, pd.Index):
        data = pd.Series(data, dtype=object)

    if isinstance(data, pd.DataFrame):
        for column in data.columns:
            data[column] = filter_empty_values(data[column])
        return data

    if data.dtype.name == "category":
        valid_categories = [cat for cat in data.cat.categories if cat != ""]
        data = data.cat.set_categories(valid_categories)
        data = data[data.notnull()]
        return data[data.notna()]

    else:
        data = data.astype("object").map(str)
        data.loc[data == ""] = np.nan  # Replace empty strings manually
        data = data[data.index != ""]
        data = data[data.index.notnull()]
        return data.dropna()
