import math
import os

import geopandas as gpd
import pandas as pd

from get_and_transform_data import get_and_transform_data
from utils.rivers import linear_flow

PHOSPHORUS_TO_ORTHOPHOSPHATE_EFFLUENT = 0.785

WWTW_PHOSPHORUS_FILL_VALUE = 5.0  # mg/l
WWTW_DWF_FILL_VALUE = 20.0  # m3/day

CSO_PHOSPHORUS_FILL_VALUE = 3.0  # mg/l
CSO_WEIR_SETTING_FILL_VALUE = 20  # l/s

P_GUIDELINE = 0.87  # mg/l
P_DEGRADATION_COEFF = 4e-2  # /day

FLOW_SPEED = 0.77  # m/s

DATA_DIR = "./data/"
DET_PATH = DATA_DIR + "determinands.parquet"
WWTW_PATH = DATA_DIR + "wwtw.parquet"
CSO_PATH = DATA_DIR + "cso.parquet"
if (
    not os.path.exists(DET_PATH)
    or not os.path.exists(WWTW_PATH)
    or not os.path.exists(CSO_PATH)
):
    _ = get_and_transform_data()

determinands = pd.read_parquet("./data/determinands.parquet")

##############################################################################
wwtw = gpd.read_parquet("./data/wwtw.parquet")

wwtw_join = wwtw.join(
    determinands[
        determinands["DETE"].str.contains("Phosphorus")
        & (determinands["CODE"] == "MEAN VALUE")
    ]["VALUE"],
    how="left",
)
wwtw_join.rename(columns={"VALUE": "P"}, inplace=True)

wwtw_join = wwtw_join.join(
    determinands[
        (determinands["DETE"].str.contains("Flow : Dry Weather :- {DWF}"))
        & (determinands["CODE"] == "MAXIMUM VALUE")
    ]["VALUE"],
    how="left",
)
wwtw_join.rename(columns={"VALUE": "DWF"}, inplace=True)

wwtw_join["P"] = wwtw_join["P"] * PHOSPHORUS_TO_ORTHOPHOSPHATE_EFFLUENT
wwtw_join.fillna({"P": WWTW_PHOSPHORUS_FILL_VALUE}, inplace=True)
wwtw_join.fillna({"DWF": WWTW_DWF_FILL_VALUE}, inplace=True)

##############################################################################

cso = gpd.read_parquet("./data/cso.parquet")

cso_join = cso.join(
    determinands[
        (determinands["DETE_CODE"] == 8174)
        & (determinands["CODE"] == "MINIMUM VALUE")
    ]["VALUE"],
    how="left",
    on="ID",
)
cso_join.rename(columns={"VALUE": "Weir Setting"}, inplace=True)

cso_join.fillna({"Weir Setting": CSO_WEIR_SETTING_FILL_VALUE}, inplace=True)

#############################################################################


def add_wwtw_p_risk(id: str, river_info: dict) -> float:
    """
    Calculate the risk from phosphorus emissions by wastewater treatment works.

    Parameters
    ----------
    id : str
        The ID of the treatment work.
    river_info : dict
        A dictionary of river information at the point of inflow into the river network.

    Returns
    -------
    float
        The phosphorus risk value scaled between 0 and 100.
    """
    accum_len = river_info["US_Accum"]
    # Convert P consent to orthophosphate
    p = wwtw_join.loc[id, "P"]
    dwf = wwtw_join.loc[id, "DWF"]
    p_dilution = p * dwf / (linear_flow(accum_len) * 86400)
    rsk = p_dilution / P_GUIDELINE * 100
    return rsk


def get_wwtw_values() -> pd.DataFrame:
    """
    Returns a DataFrame with the phosphorus and dry weather flow values for each wastewater treatment works.

    Returns
    -------
    pd.DataFrame
        The dataframe containing the phosphorus and dry weather flow values.
    """
    return wwtw_join[["P", "DWF"]]


def add_cso_p_risk(id: str, river_info: dict) -> float:
    """
    Calculate the risk from combined sewer overflows based on weir settings and spill duration.

    Parameters
    ----------
    id : str
        The unique ID of the CSO.
    river_info : dict
        A dictionary of river information containing the upstream accumulated length.

    Returns
    -------
    float
        The phosphorus risk value scaled between 0 and 100.
    """
    accum_len = river_info["US_Accum"]
    p = CSO_PHOSPHORUS_FILL_VALUE
    weir_setting = cso_join.loc[id, "Weir Setting"]  # l/s

    time = cso_join.loc[id, "SpillDuration"]
    seconds = time.total_seconds() if not pd.isna(time) else 0

    p_dilution = (
        p
        * weir_setting
        / (linear_flow(accum_len) * 1000)
        * (seconds / (365 * 24 * 60 * 60))
    )
    rsk = p_dilution / P_GUIDELINE * 100
    return rsk


def get_cso_values() -> pd.DataFrame:
    """
    Returns a DataFrame with the phosphorus values for each combined sewer overflow.

    Returns
    -------
    pd.DataFrame
        The dataframe containing the phosphorus values.
    """
    return cso_join[["Weir Setting"]]


def p_distance_scaling(x: float) -> float:
    if x < 0:
        return 0
    return math.e ** (-(P_DEGRADATION_COEFF / 86400) * x / FLOW_SPEED)
