import os
import pathlib
from typing import Callable

import geopandas as gpd
import pandas as pd

from get_and_transform_data import get_and_transform_data
from pollutant_parameters import NH4_values, P_values

# For water companies
WWTW_DWF_FILL_VALUE = 20.0  # m3/day
# For private discharges
WWTW_PRIVATE_A0_DWF_FILL_VALUE = 0.8  # m3/day
WWTW_PRIVATE_A1_DWF_FILL_VALUE = 7  # m3/day

CSO_WEIR_SETTING_FILL_VALUE = 20  # l/s

DATA_DIR = pathlib.Path(__file__).parent.parent.joinpath("data")
DET_PATH = DATA_DIR.joinpath("determinands.parquet")
WWTW_PATH = DATA_DIR.joinpath("wwtw.parquet")
CSO_PATH = DATA_DIR.joinpath("cso.parquet")

if (
    not os.path.exists(DET_PATH)
    or not os.path.exists(WWTW_PATH)
    or not os.path.exists(CSO_PATH)
):
    _ = get_and_transform_data()

determinands = pd.read_parquet(DET_PATH)

##############################################################################
wwtw = gpd.read_parquet(WWTW_PATH)

# Phosphorus values
wwtw_join = wwtw.join(
    determinands[
        (determinands["DETE_CODE"] == 348)
        & (determinands["CODE"] == "MEAN VALUE")
    ]["VALUE"],
    how="left",
)
wwtw_join.rename(columns={"VALUE": "P"}, inplace=True)

# Ammonaical Nitrogen values
wwtw_join = wwtw_join.join(
    determinands[
        (
            (determinands["DETE_CODE"] == 111)
            & (determinands["CODE"] == "MAXIMUM VALUE")
        )
    ]["VALUE"],
    how="left",
)
wwtw_join.rename(columns={"VALUE": "NH4"}, inplace=True)

# Dry weather flow values
wwtw_join = wwtw_join.join(
    determinands[
        (determinands["DETE_CODE"] == 7782)
        & (determinands["CODE"] == "MAXIMUM VALUE")
    ]["VALUE"],
    how="left",
)
wwtw_join.rename(columns={"VALUE": "DWF"}, inplace=True)

wwtw_join["P"] = (
    wwtw_join["P"] * P_values.PHOSPHORUS_TO_ORTHOPHOSPHATE_EFFLUENT
)
wwtw_join.fillna({"P": P_values.WWTW_PHOSPHORUS_FILL_VALUE}, inplace=True)
wwtw_join.fillna({"NH4": NH4_values.WWTW_NH4_FILL_VALUE}, inplace=True)

# Fill missing values dry weather flow for different
# discharge site types
wwtw_join.loc[
    (wwtw_join["DISCHARGE_SITE_TYPE_CODE"] == "A0") & wwtw_join["DWF"].isna(),
    "DWF",
] = WWTW_PRIVATE_A0_DWF_FILL_VALUE
wwtw_join.loc[
    (wwtw_join["DISCHARGE_SITE_TYPE_CODE"] == "A1") & wwtw_join["DWF"].isna(),
    "DWF",
] = WWTW_PRIVATE_A1_DWF_FILL_VALUE
wwtw_join.loc[
    (wwtw_join["DISCHARGE_SITE_TYPE_CODE"] == "A2") & wwtw_join["DWF"].isna(),
    "DWF",
] = WWTW_DWF_FILL_VALUE


##############################################################################

cso = gpd.read_parquet(CSO_PATH)

# Weir setting values
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


def add_wwtw_risk(
    parameter: str,
) -> Callable[[str, float], float]:
    if parameter == "P":
        return add_wwtw_p_risk
    elif parameter == "NH4":
        return add_wwtw_nh4_risk
    else:
        raise NotImplementedError("Parameter not implemented.")


def add_wwtw_p_risk(id: str, river_flow: float) -> float:
    """
    Calculate the risk from phosphorus emissions by wastewater treatment works.

    Parameters
    ----------
    id : str
        The ID of the treatment work.
    river_flow : float
        The value of the river flow in m3/s

    Returns
    -------
    float
        The phosphorus risk value scaled between 0 and 100.
    """
    # Convert P consent to orthophosphate
    p = wwtw_join.loc[id, "P"]
    dwf = wwtw_join.loc[id, "DWF"]
    p_dilution = p * dwf / (river_flow * 86400)
    rsk = p_dilution / P_values.P_GUIDELINE * 100
    return rsk


def add_wwtw_nh4_risk(id: str, river_flow: float) -> float:
    """
    Calculate the risk from ammoniacal nitrogen emissions by wastewater treatment works.

    Parameters
    ----------
    id : str
        The ID of the treatment work.
    river_flow : float
        The value of the river flow in m3/s

    Returns
    -------
    float
        The ammoniacal nitrogen risk value scaled between 0 and 100.
    """
    nh4 = wwtw_join.loc[id, "NH4"]
    dwf = wwtw_join.loc[id, "DWF"]
    nh4_dilution = nh4 * dwf / (river_flow * 86400)
    rsk = nh4_dilution / NH4_values.NH4_GUIDELINE * 100
    return rsk


def get_wwtw_values(parameters: list[str]) -> pd.DataFrame:
    """
    Returns a DataFrame with the specified parameters for each wastewater treatment works.

    Parameters
    ----------
    parameters : list[str]
        List of parameters to include in the DataFrame. By default, it includes the DWF and discharge site type code.

    Returns
    -------
    pd.DataFrame
        The dataframe containing the parameter and dry weather flow values.
    """
    return wwtw_join[parameters + ["DWF", "DISCHARGE_SITE_TYPE_CODE"]].copy()


def add_cso_risk(
    parameter: str,
) -> Callable[[str, float], float]:
    if parameter == "P":
        return add_cso_p_risk
    elif parameter == "NH4":
        return add_cso_nh4_risk
    else:
        raise NotImplementedError("Parameter not implemented.")


def add_cso_p_risk(id: str, river_flow: float) -> float:
    """
    Calculate the risk from combined sewer overflows based on weir settings and spill duration.

    Parameters
    ----------
    id : str
        The unique ID of the CSO.
    river_flow : float
        The value of the river flow in m3/s.

    Returns
    -------
    float
        The phosphorus risk value scaled between 0 and 100.
    """
    p = P_values.CSO_PHOSPHORUS_FILL_VALUE
    weir_setting: int = cso_join.loc[id, "Weir Setting"]  # l/s

    time = cso_join.loc[id, "SpillDuration"]
    seconds = time.total_seconds() if not pd.isna(time) else 0

    p_dilution = (
        p
        * weir_setting
        / (river_flow * 1000)
        * (seconds / (365 * 24 * 60 * 60))
    )
    rsk = p_dilution / P_values.P_GUIDELINE * 100
    return rsk


def add_cso_nh4_risk(id: str, river_flow: float) -> float:
    """
    Calculate the risk from ammoniacal nitrogen emissions by combined sewer overflows.

    Parameters
    ----------
    id : str
        The unique ID of the CSO.
    river_flow : float
        The value of the river flow in m3/s.

    Returns
    -------
    float
        The ammoniacal nitrogen risk value scaled between 0 and 100.
    """
    nh4 = NH4_values.CSO_NH4_FILL_VALUE
    weir_setting = cso_join.loc[id, "Weir Setting"]  # l/s

    time = cso_join.loc[id, "SpillDuration"]
    seconds = time.total_seconds() if not pd.isna(time) else 0

    nh4_dilution = (
        nh4
        * weir_setting
        / (river_flow * 1000)
        * (seconds / (365 * 24 * 60 * 60))
    )
    rsk = nh4_dilution / NH4_values.NH4_GUIDELINE * 100
    return rsk


def get_cso_values(parameters: list[str]) -> pd.DataFrame:
    """
    Returns a DataFrame with the specified parameters for each combined sewer overflow.

    Parameters
    ----------
    parameters : list[str]
        List of parameters to include in the DataFrame. By default, it includes the weir setting and spill duration.
    Returns
    -------
    pd.DataFrame
        The dataframe containing the parameter values.
    """

    cso_join2 = cso_join.copy()
    cso_join2["P"] = P_values.CSO_PHOSPHORUS_FILL_VALUE
    cso_join2["NH4"] = NH4_values.CSO_NH4_FILL_VALUE
    return cso_join2[
        parameters
        + [
            "Weir Setting",
        ]
    ]
