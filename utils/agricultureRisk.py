import pathlib

import geopandas as gpd
import numpy as np
import pandas as pd

import get_and_transform_data

land_cover_data = None
catchments_used = None


# Defining land cover categories from the land cover data
GRASS = [4]
ROUGH = [0]
ARABLE = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13]

# Define paths for loading
DATA_FOLDER = pathlib.Path(__file__).parent.parent.joinpath("data")
AGRICULTURE_LOAD_LOOKUP_PATH = DATA_FOLDER.joinpath("agriculture_load_lookup.csv")
LIVESTOCK_EXCRETA_PATH = DATA_FOLDER.joinpath("livestock_excreta.csv")
EXCRETA_LOAD_PATH = DATA_FOLDER.joinpath("livestock_excreta_load.csv")

# Load all dataframes
AGRICULTURE_LOAD_LOOKUP = pd.read_csv(
    AGRICULTURE_LOAD_LOOKUP_PATH,
    index_col=["crop_category", "soil_category", "rainfall_category"],
)
LIVESTOCK_EXCRETA = pd.read_csv(
    LIVESTOCK_EXCRETA_PATH, index_col=["OPCAT_ID", "crop_category"]
)
ENG_CATCH = gpd.read_file(
    "https://environment.data.gov.uk/catchment-planning/England/shapefile.zip",
    layer="WFD_Surface_Water_Operational_Catchments_Cycle_3",
).astype({"OPCAT_ID": "int16"})
EXCRETA_LOAD = pd.read_csv(
    EXCRETA_LOAD_PATH,
    index_col=[
        "crop_category",
        "soil_category",
        "rainfall_category",
        "livestock_category",
    ],
)


def runoff_scaling(dist: float) -> float:
    """
    Calculate the scaling factor for phosphorus in the case of runoff.

    Parameters
    ----------
    dist : float
        Distance from the river in meters.
    If the distance is negative, it returns 0.

    Returns
    -------
    float
        Scaling factor for phosphorus.
    """
    if dist < 0:
        return 0
    else:
        return np.exp(-dist / 100)


def agriculture_land_cover_load(
    rmap,
    parameter: str,
) -> gpd.GeoDataFrame:
    """
    Calculate the agriculture land cover risk based on the provided risk map.

    Parameters
    ----------
    rmap : gpd.GeoDataFrame
        GeoDataFrame containing the risk map with geometry and river index.
    parameter : str
        Parameter to calculate the land cover load for ("P" or "NH4").

    Returns
    -------
    gpd.GeoDataFrame
        DataFrame containing the calculated agriculture land cover risk.
    """
    global land_cover_data, catchments_used
    joined_catchments, _, mapping_points = rmap.get_joined_catchments()
    if land_cover_data is None or not joined_catchments.equals(catchments_used):
        land_cover_data = get_and_transform_data.get_land_cover_data(joined_catchments)
        catchments_used = joined_catchments

    # Join the land cover data with the joined polygons
    combined = gpd.overlay(
        land_cover_data,
        joined_catchments.reset_index(drop=False),
        how="intersection",
        keep_geom_type=True,
    )

    # Calculate the distance of each polygon from its closest point in the river
    all_rivs = gpd.GeoDataFrame(
        geometry=[rmap.get_rivers().geometry.union_all()], crs=rmap.get_rivers().crs
    )
    riv_catch = gpd.overlay(
        all_rivs,
        joined_catchments.reset_index(drop=False),
        keep_geom_type=True,
        make_valid=True,
    )

    mypoints = mapping_points[
        (mapping_points["FID"].notna())
        & (~mapping_points["FID"].isin(riv_catch["FID_poly"]))
    ].rename(columns={"FID": "FID_poly"})
    all_points = pd.concat(
        [riv_catch, mypoints[["geometry", "FID_poly"]]], ignore_index=True
    )
    all_points = gpd.GeoDataFrame(all_points)

    combined_dist = combined.join(
        all_points.rename(columns={"geometry": "river_section"}).set_index(
            "FID_poly", drop=True
        ),
        on="FID_poly",
        how="left",
        validate="m:1",
    )
    combined_dist["distance"] = combined_dist["geometry"].distance(
        combined_dist["river_section"]
    )
    combined_dist.drop(columns=["river_section"], inplace=True)

    final_with_load = combined_dist.join(
        AGRICULTURE_LOAD_LOOKUP,
        how="left",
        on=["crop_category", "soil_category", "rainfall_category"],
    )

    # Choose parameter
    if parameter == "P":
        # Load the lookup tables for P load
        final_with_load["load"] = (
            final_with_load["P_load"] * 1000 / (365 * 60 * 60 * 24)
        )  # Convert from kg/m2/year to g/m2/s
    elif parameter == "NH4":
        final_with_load["load"] = (
            final_with_load["NH4_load"] * 1000 / (365 * 60 * 60 * 24)
        )  # Convert from kg/m2/year to g/m2/s
    else:
        raise NotImplementedError("Parameter not implemented.")

    # Apply distance scaling to the load
    final_with_load.loc[final_with_load["Pathway"] == 1, "load"] *= final_with_load.loc[
        final_with_load["Pathway"] == 1, "distance"
    ].apply(runoff_scaling)
    # Scale the load by the area of the polygon
    final_with_load["load"] *= final_with_load["geometry"].area
    final_with_load.fillna({"load": 0}, inplace=True)
    return final_with_load


def agriculture_livestock_load(
    rmap,
    parameter: str,
) -> gpd.GeoDataFrame:
    """
    Calculate the agriculture livestock risk from excreta
    based on the provided risk map.

    Parameters
    ----------
    rmap : RiskMap
        RiskMap object containing the risk map data.
    parameter : str
        Parameter to calculate the livestock load for ("P" or "NH4").
    Returns
    -------
    gpd.GeoDataFrame
        DataFrame containing the calculated agriculture livestock load.
    """
    global land_cover_data, catchments_used
    joined_catchments, _, mapping_points = rmap.get_joined_catchments()
    # Check if land cover data is already loaded and matches the current catchments
    if land_cover_data is None or not joined_catchments.equals(catchments_used):
        land_cover_data = get_and_transform_data.get_land_cover_data(joined_catchments)
        catchments_used = joined_catchments
    # Join the land cover data with the joined polygons
    combined = gpd.overlay(
        land_cover_data,
        joined_catchments.reset_index(drop=False),
        how="intersection",
        keep_geom_type=True,
    )

    # Calculate the distance of each polygon from its closest point in the river
    all_rivs = gpd.GeoDataFrame(
        geometry=[rmap.get_rivers().geometry.union_all()], crs=rmap.get_rivers().crs
    )
    riv_catch = gpd.overlay(
        all_rivs,
        joined_catchments.reset_index(drop=False),
        keep_geom_type=True,
        make_valid=True,
    )

    mypoints = mapping_points[
        (mapping_points["FID"].notna())
        & (~mapping_points["FID"].isin(riv_catch["FID_poly"]))
    ].rename(columns={"FID": "FID_poly"})
    all_points = pd.concat(
        [riv_catch, mypoints[["geometry", "FID_poly"]]], ignore_index=True
    )
    all_points = gpd.GeoDataFrame(all_points)

    combined_dist = combined.join(
        all_points.rename(columns={"geometry": "river_section"}).set_index(
            "FID_poly", drop=True
        ),
        on="FID_poly",
        how="left",
        validate="m:1",
    )
    combined_dist["distance"] = combined_dist["geometry"].distance(
        combined_dist["river_section"]
    )
    combined_dist.drop(columns=["river_section"], inplace=True)

    livestock_final = gpd.overlay(
        combined_dist,
        ENG_CATCH.to_crs(combined_dist.crs)[["geometry", "OPCAT_ID"]],
        how="intersection",
        keep_geom_type=True,
    )

    # Reclassify land cover categories
    def reclassify_crop_category(crop_category):
        if crop_category is None:
            return None
        elif crop_category in GRASS:  # Grass
            return 4
        elif crop_category in ROUGH:
            return 0
        elif crop_category in ARABLE:  # Arable
            return -1
        else:
            return crop_category

    livestock_final["crop_category"] = livestock_final["crop_category"].apply(
        reclassify_crop_category
    )

    # Get the excreta per hectare
    final_with_excreta = livestock_final.join(
        LIVESTOCK_EXCRETA,
        how="left",
        on=["OPCAT_ID", "crop_category"],
    )
    # Get the excreta per polygon
    final_with_excreta["excreta"] = final_with_excreta.apply(
        lambda x: (
            (x["excreta_per_ha"] * x["geometry"].area / 10000)
            if pd.notna(x["excreta_per_ha"])
            else 0
        ),
        axis=1,
    )
    final_with_excreta.drop(columns=["excreta_per_ha"], inplace=True)

    # Get load per polygon
    final_with_load = final_with_excreta.join(
        EXCRETA_LOAD,
        on=[
            "crop_category",
            "soil_category",
            "rainfall_category",
            "livestock_category",
        ],
        how="left",
    )

    # Choose Parameter
    if parameter == "P":
        # Convert from kg/year to g/s
        final_with_load["load"] = (
            final_with_load["excreta"]
            * final_with_load["P_load"]
            * 1000
            / (365 * 60 * 60 * 24)
        )
    elif parameter == "NH4":
        # Convert from kg/year to g/s
        final_with_load["load"] = (
            final_with_load["excreta"]
            * final_with_load["NH4_load"]
            * 1000
            / (365 * 60 * 60 * 24)
        )
    else:
        raise NotImplementedError("Parameter not implemented.")

    # Apply distance scaling to the load for runoff
    final_with_load.loc[final_with_load["Pathway"] == 1, "load"] *= final_with_load.loc[
        final_with_load["Pathway"] == 1, "distance"
    ].apply(runoff_scaling)
    final_with_load.fillna({"load": 0}, inplace=True)
    return final_with_load
