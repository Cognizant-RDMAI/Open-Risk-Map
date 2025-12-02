import numpy as np

PHOSPHORUS_TO_ORTHOPHOSPHATE_EFFLUENT = 0.785
P_GUIDELINE = 0.87  # mg/l
P_DEGRADATION_COEFF = 4e-2  # /day

# For water companies
WWTW_PHOSPHORUS_FILL_VALUE = 5.0  # mg/l
CSO_PHOSPHORUS_FILL_VALUE = 3.0  # mg/l

# Urban risk
ROAD_P_RUNOFF = 0.1  # mg/l
BUILD_P_RUNOFF = 0.1  # mg/l

FLOW_SPEED = 0.77  # m/s


def p_distance_scaling(x: float | list | np.ndarray) -> float | np.ndarray:
    x = np.asarray(x)
    result = np.where(
        x < 0, 0, np.exp(-(P_DEGRADATION_COEFF / 86400) * x / FLOW_SPEED)
    )
    if result.ndim == 0:
        return float(result)
    return result
