import pathlib

import geopandas as gpd
import pandas as pd

from get_and_transform_data import get_rainfall_data
from pollutant_parameters import NH4_values, P_values

RURAL_ROAD_RIVER_DISTANCE: float = 200.0

joined_catchments_before = None

combined_roads = None
combined_builds = None

DATA_FOLDER = pathlib.Path(__file__).parent.parent.joinpath("data")
ROAD_WIDTH_LOOKUP_PATH = DATA_FOLDER.joinpath("road_width_lookup.csv")
BUILTUP_PATH = DATA_FOLDER.joinpath("os_builtup.parquet")
ROADS_PATH = DATA_FOLDER.joinpath("os_roads.parquet")
BUILDINGS_PATH = DATA_FOLDER.joinpath("os_buildings.parquet")

RAINFALL = get_rainfall_data()  # mm/year
ROAD_WIDTH = pd.read_csv(
    ROAD_WIDTH_LOOKUP_PATH, index_col="classification"
)  # m
BUILTUP = gpd.read_parquet(BUILTUP_PATH)


def urban_road(
    rmap,
    parameter: str,
) -> gpd.GeoDataFrame:
    """
    Calculate the urban road load based on the provided risk map and the parameter

    Parameters
    ----------
    rmap : RiskMap
        RiskMap object containing the risk map with geometry and river index.

    parameter : str
        The parameter to calculate risk for, either "P" or "NH4".

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame containing the urban road load for the given parameter.
    """
    global joined_catchments_before, combined_roads
    joined_catchments = rmap.get_joined_catchments(copy=False)[0]
    rivers = rmap.get_rivers(copy=False)

    if combined_roads is None or not joined_catchments_before.equals(
        joined_catchments
    ):
        road = gpd.read_parquet(
            ROADS_PATH, bbox=joined_catchments.total_bounds
        )[["geometry", "id", "classification"]].overlay(
            joined_catchments.reset_index(),
            how="intersection",
            keep_geom_type=True,
        )
        road = road.join(
            ROAD_WIDTH, on="classification", how="left"
        ).reset_index()
        urb_roads = gpd.overlay(
            road,
            BUILTUP,
            how="intersection",
            keep_geom_type=True,
        )
        urb_roads["urban"] = True

        rur_roads = gpd.overlay(
            road,
            BUILTUP,
            how="difference",
            keep_geom_type=True,
        )
        rur_roads["urban"] = False
        roads = pd.concat([urb_roads, rur_roads], ignore_index=True)
        riverbuffer = gpd.GeoDataFrame(
            geometry=rivers.buffer(RURAL_ROAD_RIVER_DISTANCE), crs=rivers.crs
        )

        riv_roads = gpd.overlay(
            roads,
            riverbuffer,
            how="intersection",
            keep_geom_type=True,
        )
        riv_roads["river"] = True

        non_riv_roads = gpd.overlay(
            roads,
            riverbuffer,
            how="difference",
            keep_geom_type=True,
        )
        non_riv_roads["river"] = False
        roads = pd.concat([riv_roads, non_riv_roads], ignore_index=True)

        combined_roads = gpd.overlay(
            roads,
            RAINFALL,
            how="intersection",
            keep_geom_type=True,
        )
        combined_roads["area"] = (
            combined_roads.geometry.length * combined_roads["width"]
        )

    # Assign Risk
    combined_roads["load"] = 0.0

    if parameter == "P":
        combined_roads.loc[combined_roads["urban"], "load"] = (
            combined_roads["area"]
            * P_values.ROAD_P_RUNOFF
            * combined_roads["pr"]
        )
        combined_roads.loc[
            ~combined_roads["urban"] & combined_roads["river"], "load"
        ] = (
            combined_roads["area"]
            * P_values.ROAD_P_RUNOFF
            * combined_roads["pr"]
        )
    elif parameter == "NH4":
        combined_roads.loc[combined_roads["urban"], "load"] = (
            combined_roads["area"]
            * NH4_values.ROAD_URBAN_NH4_RUNOFF
            * combined_roads["pr"]
        )
        combined_roads.loc[
            ~combined_roads["urban"] & combined_roads["river"], "load"
        ] = (
            combined_roads["area"]
            * NH4_values.ROAD_RURAL_NH4_RUNOFF
            * combined_roads["pr"]
        )
    else:
        raise NotImplementedError("Parameter not implemented.")

    combined_roads["load"] *= 1 / (
        1000 * 365 * 24 * 60 * 60
    )  # Convert from mg/year to g/s

    joined_catchments_before = joined_catchments
    return combined_roads


def urban_buildings(
    rmap,
    parameter: str,
) -> gpd.GeoDataFrame:
    """
    Calculate the urban building load based on the provided risk map for the
    given parameter.

    Parameters
    ----------
    rmap : RiskMap
        RiskMap object containing the risk map with geometry and river index.

    parameter : str
        The parameter to calculate risk for, either "P" or "NH4".

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame containing the urban building load
    """
    global joined_catchments_before, combined_builds
    joined_catchments = rmap.get_joined_catchments(copy=False)[0]

    if combined_builds is None or not joined_catchments_before.equals(
        joined_catchments
    ):
        build = gpd.read_parquet(
            BUILDINGS_PATH, bbox=joined_catchments.total_bounds
        ).overlay(
            joined_catchments.reset_index(),
            how="intersection",
            keep_geom_type=True,
        )
        urb_builds = gpd.overlay(
            build,
            BUILTUP,
            how="intersection",
            keep_geom_type=True,
        )
        urb_builds["urban"] = True

        rur_builds = gpd.overlay(
            build,
            BUILTUP,
            how="difference",
            keep_geom_type=True,
        )
        rur_builds["urban"] = False
        builds = pd.concat([urb_builds, rur_builds], ignore_index=True)

        combined_builds = gpd.overlay(
            builds,
            RAINFALL,
            how="intersection",
            keep_geom_type=True,
        )
        combined_builds["area"] = combined_builds.geometry.area
    combined_builds["load"] = 0.0

    if parameter == "P":
        combined_builds.loc[combined_builds["urban"], "load"] = (
            combined_builds["area"]
            * P_values.BUILD_P_RUNOFF
            * combined_builds["pr"]
        )
    elif parameter == "NH4":
        combined_builds.loc[combined_builds["urban"], "load"] = (
            combined_builds["area"]
            * NH4_values.BUILD_NH4_RUNOFF
            * combined_builds["pr"]
        )
    else:
        raise NotImplementedError("Parameter not implemented.")
    combined_builds["load"] *= 1 / (
        1000 * 365 * 24 * 60 * 60
    )  # Convert from mg/year to g/s

    joined_catchments_before = joined_catchments
    return combined_builds
