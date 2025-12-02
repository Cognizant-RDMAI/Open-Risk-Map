import numpy as np

NH4_GUIDELINE = 6.0  # mg/l
NH4_DEGRADATION_COEFF = 0.42  # /day

# For water companies
WWTW_NH4_FILL_VALUE = 2.6  # mg/l
CSO_NH4_FILL_VALUE = 13  # mg/l

# Urban risk
ROAD_URBAN_NH4_RUNOFF = 0.8  # mg/l
ROAD_RURAL_NH4_RUNOFF = 0.65  # mg/l
BUILD_NH4_RUNOFF = 0.2  # mg/l

FLOW_SPEED = 0.77  # m/s


def nh4_distance_scaling(x: float | list | np.ndarray) -> float | np.ndarray:
    x = np.asarray(x)
    result = np.where(
        x < 0, 0, np.exp(-(NH4_DEGRADATION_COEFF / 86400) * x / FLOW_SPEED)
    )
    if result.ndim == 0:
        return float(result)
    return result
