import io
import logging
import os
import pathlib
import subprocess
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely
from fuzzywuzzy import fuzz
from OSGridConverter import grid2latlong

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

DATA_DIR: pathlib.Path = pathlib.Path(__file__).parent.joinpath("data")
OUTPUT_ESPG: int = 27700


def get_lat_lon(x):
    """
    Convert a grid reference to latitude and longitude.

    Parameters
    ----------
    x : str
        Grid reference.

    Returns
    -------
    shapely.Point or None
        A shapely Point object with longitude and latitude, or None if
        conversion fails.
    """
    try:
        latlong = grid2latlong(x)
        return shapely.Point(latlong.longitude, latlong.latitude)
    except Exception as e:
        logger.error(f"Failed to convert grid reference {x} to lat/lon: {e}")
        return None


def get_cso_annual_data(repeat: bool = False) -> gpd.GeoDataFrame:
    """
    Downloads and transforms CSO annual data.

    Parameters
    ----------
    repeat : bool, optional
        If True, forces redownload and transformation of data, by default
        False.

    Returns
    -------
    gpd.GeoDataFrame
        Transformed CSO annual data as a GeoDataFrame.
    """
    annual_path = DATA_DIR.joinpath("annual")
    # CSO data
    cso_path = annual_path.joinpath("cso.parquet")

    if os.path.exists(cso_path) and not repeat:
        logger.info("CSO data found")
        return gpd.read_parquet(cso_path)

    logger.info("Downloading CSO data...")
    cso_url = (
        "https://environment.data.gov.uk/"
        "file-management-open/data-sets/"
        "c55e170e-3c75-49a5-8026-a961ff94c8e0/files"
        "/EDM_2024_Storm_Overflow_Annual_Return.zip"
    )

    try:
        request = requests.get(cso_url, timeout=100)
        with zipfile.ZipFile(io.BytesIO(request.content)) as arc:
            arc.extractall(annual_path)
    except Exception as e:
        logger.error(f"Failed to download or extract CSO data: {e}")
        raise

    logger.info("Transforming CSO data...")
    try:
        df = pd.read_excel(
            annual_path.joinpath(
                "EDM_2024_Storm_Overflow_Annual_Return",
                "EDM 2024 Storm Overflow Annual Return "
                + "- all water and sewerage companies.xlsx",
            ),
            header=1,
            sheet_name=None,
            index_col=None,
        )
        annual = pd.concat(df.values())

        # Set the location of the CSOs according to the data
        ngrs = annual["Outlet Discharge NGR\n(EA Consents Database)"].apply(
            lambda x: x.split(" ")[0].split(",")[0]
        )  # Choose only the first NGR
        annual["geometry"] = ngrs.apply(get_lat_lon)

        annual = gpd.GeoDataFrame(
            annual, geometry="geometry", crs="EPSG:4326"
        ).to_crs(epsg=OUTPUT_ESPG)

        for col in annual.columns:
            if annual[col].dtype == "object":
                annual[col] = annual[col].astype(str).str.strip()
        annual.to_parquet(cso_path, index=False)
        logger.info("CSO data downloaded and transformed")
    except Exception as e:
        logger.error(f"Failed to transform CSO data: {e}")
        raise

    return annual


def get_consents_data(
    repeat: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Downloads and extracts consents and determinands data.

    Parameters
    ----------
    repeat : bool, optional
        If True, forces redownload and extraction of data, by default False.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        A tuple containing consents and determinands data as DataFrames.
    """
    os.makedirs(DATA_DIR.joinpath("consentsdb"), exist_ok=True)
    consentsdb_path = DATA_DIR.joinpath("consentsdb")
    consents_path = pathlib.Path.joinpath(consentsdb_path, "consents.csv")
    det_path = pathlib.Path.joinpath(consentsdb_path, "determinands.csv")

    if (
        os.path.exists(consents_path)
        and os.path.exists(det_path)
        and not repeat
    ):
        logger.info("Consents data found")
        return (
            pd.read_csv(consents_path),
            pd.read_csv(det_path, low_memory=False),
        )
    # Check if the consents data is already downloaded

    if (
        os.path.exists(
            consentsdb_path.joinpath(
                "Consented Discharges to Controlled Waters with "
                "Conditions.accdb"
            )
        )
        and not repeat
    ):
        logger.info("Downloaded consents data found...")

    else:
        logger.info("Downloading consents data...")
        consents_url = (
            "https://environment.data.gov.uk/api/file/download"
            "?fileDataSetId=a54fdea1-7769-4b22-a518-10d51fed6f33&"
            "fileName=Consented%20Discharges%20to%20Controlled%20"
            "Waters%20with%20Conditions.zip"
        )
        try:
            request = requests.get(consents_url, timeout=1000)
            with zipfile.ZipFile(io.BytesIO(request.content)) as arc:
                arc.extractall(consentsdb_path)
        except Exception as e:
            logger.error(f"Failed to download or extract consents data: {e}")
            raise

    try:
        with open(det_path, "w") as det_file:
            subprocess.run(
                [
                    "mdb-export",
                    str(
                        consentsdb_path.joinpath(
                            (
                                "Consented Discharges to Controlled"
                                " Waters with Conditions.accdb"
                            )
                        )
                    ),
                    "determinands",
                ],
                stdout=det_file,
                check=True,
            )

        with open(consents_path, "w") as consents_file:
            subprocess.run(
                [
                    "mdb-export",
                    str(
                        consentsdb_path.joinpath(
                            (
                                "Consented Discharges to Controlled"
                                " Waters with Conditions.accdb"
                            )
                        )
                    ),
                    "consents_active",
                ],
                stdout=consents_file,
                check=True,
            )
        logger.info("Consents data downloaded and extracted")
    except Exception as e:
        logger.error(f"Failed to extract consents data: {e}")
        raise

    consents = pd.read_csv(consents_path)
    determinands = pd.read_csv(det_path, low_memory=False)
    return consents, determinands


def get_rivers_data(repeat: bool = False) -> gpd.GeoDataFrame:
    """getRiversData downloads and transforms the Open Rivers Network data

    Parameters
    ----------
    repeat : bool, optional
        Redownloads if present, by default False

    Returns
    -------
    gpd.GeoDataFrame
        The rivers data as a GeoDataFrame from ORN
    """
    if os.path.exists(DATA_DIR.joinpath("rivers.geojson")) and not repeat:
        logger.info("Rivers data found")
        return gpd.read_file(DATA_DIR.joinpath("rivers.geojson"))
    logger.info("Downloading rivers data...")
    try:
        rivers = gpd.read_file(
            "https://openrivers.net/download/ORN_v2_GeoPackage.zip",
            layer="ORN",
        )
        rivers.to_crs(epsg="27700", inplace=True)
        rivers.to_file(DATA_DIR.joinpath("rivers.geojson"))
        logger.info("Rivers data downloaded and transformed")
    except Exception as e:
        logger.error(f"Failed to download or transform rivers data: {e}")
        raise
    return rivers


def consents_transform(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Transforms consents data into a GeoDataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Consents data.

    Returns
    -------
    gpd.GeoDataFrame
        Transformed consents data as a GeoDataFrame.
    """
    df = df.drop_duplicates(
        subset=["PERMIT_NUMBER", "OUTLET_GRID_REF"], keep="first"
    )
    df = df.assign(
        ID=df.apply(
            lambda x: str(
                x["PERMIT_NUMBER"]
                + "_"
                + str(x["EFFLUENT_NUMBER"])
                + "_"
                + str(x["OUTLET_NUMBER"])
            ),
            axis=1,
        )
    )
    df.set_index("ID", inplace=True)
    df = df.assign(OUTLET_LOC=df["OUTLET_GRID_REF"].apply(get_lat_lon))
    df["geometry"] = df["OUTLET_LOC"].copy(deep=True)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.to_crs(epsg=27700)
    return gdf


def determinands_transform(determinands: pd.DataFrame) -> pd.DataFrame:
    """
    Transforms determinands data.

    Parameters
    ----------
    determinands : pd.DataFrame
        Determinands data.

    Returns
    -------
    pd.DataFrame
        Transformed determinands data.
    """
    # Transform Determinands
    dete_codes = [
        7782,  # Flow : Dry Weather :- {DWF}
        7729,  # Flow : Dry Weather : 3 in 5 Years
        135,  # Solids, Suspended at 105 C
        85,  # BOD : 5 Day ATU
        111,  # Ammoniacal Nitrogen as N
        6051,  # Iron
        348,  # Phosphorus, Total as P
        6057,  # Aluminium
        # Flow : To full treatment (Before spill to stor...
        3647,
        8174,  # Weir Setting
        6425,  # Flow : Daily total
    ]

    # Merge all the code values into a single column
    determinands = determinands[determinands["DETE_CODE"].isin(dete_codes)]
    determinands = determinands.assign(
        CODE_VALUE=determinands.apply(
            lambda x: [
                (x[f"CODE_{i}"], x[f"VAL_{i}"])
                for i in range(1, 4)
                if pd.notna(x[f"CODE_{i}"]) and pd.notna(x[f"VAL_{i}"])
            ],
            axis=1,
        )
    )
    determinands = determinands.explode("CODE_VALUE")
    determinands[["CODE", "VALUE"]] = pd.DataFrame(
        determinands["CODE_VALUE"].tolist(), index=determinands.index
    )
    determinands = determinands.drop(
        [
            "CODE_VALUE",
            "CODE_1",
            "CODE_2",
            "CODE_3",
            "VAL_1",
            "VAL_2",
            "VAL_3",
        ],
        axis=1,
    )
    determinands = determinands.reset_index(drop=True)

    # Choose only the latest version of each determinand
    version_mask = determinands.groupby(
        ["PERMIT_REF", "OUTLET_NUMBER", "EFFLUENT_NUMBER", "DETE", "CODE"]
    )["VERSION"].idxmax()
    determinands = determinands.loc[version_mask].reset_index(drop=True)
    determinands.set_index(
        determinands.apply(
            lambda x: str(
                x["PERMIT_REF"]
                + "_"
                + str(x["EFFLUENT_NUMBER"])
                + "_"
                + str(x["OUTLET_NUMBER"])
            ),
            axis=1,
        ),
        inplace=True,
    )
    return determinands


def split_consents(
    consents: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Splits consents data into WwTWs and CSOs.

    Parameters
    ----------
    consents : pd.DataFrame
        Consents data.

    Returns
    -------
    tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]
        A tuple containing WwTWs and CSOs as GeoDataFrames.
    """
    # Split consents into WwTWs and CSOs

    rec_env_codes = rec_env_codes = [
        1,  # Freshwater River
        6,  # Canal
        9,  # Estuary
        15,  # Into land then to watercourse
    ]
    wwtws = consents[
        (consents["DISCHARGE_SITE_TYPE_CODE"] == "A2")
        & (consents["EFFLUENT_TYPE"] == "SA")
        & (
            (consents["OUTLET_TYPE_CODE"] == "S")
            | (consents["OUTLET_TYPE_CODE"] == "U")
        )
        & (consents["RECEIVING_ENVIRON_TYPE_CODE"].isin(rec_env_codes))
    ]
    wwtws = consents_transform(wwtws)
    wwtws.drop(columns=["OUTLET_LOC"], inplace=True)

    effluent_types = ["SB", "SC", "SD"]
    csos = consents[consents["EFFLUENT_TYPE"].isin(effluent_types)]
    csos = consents_transform(csos)
    return wwtws, csos


def merge_annual_and_consents(
    annual: gpd.GeoDataFrame, consents: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """
    Merges annual CSO data with consents data.

    Parameters
    ----------
    annual : gpd.GeoDataFrame
        Annual CSO data.
    consents : gpd.GeoDataFrame
        Consents data.

    Returns
    -------
    gpd.GeoDataFrame
        Merged data as a GeoDataFrame.
    """
    # Find the distance between Annual data and Consents to find closest
    # matches
    consents["OUTLET_LOC"] = consents.geometry.copy(deep=True)
    distance_joined = gpd.sjoin(
        annual.set_geometry(annual.buffer(5000).rename("buffer")),
        consents[["OUTLET_LOC", "geometry", "PERMIT_NUMBER"]],
        predicate="contains",
        how="left",
    )
    distance_joined.set_geometry("geometry")
    distance_joined.drop(columns=["buffer"], inplace=True)

    distance_joined["PERMIT_NUMBER"] = distance_joined["PERMIT_NUMBER"].astype(
        "str"
    )
    # Fuzzy matching on the permit numbers to find the best match
    distance_joined["score"] = distance_joined.apply(
        lambda x: max(
            fuzz.ratio(
                x["EA Permit Reference\n(EA Consents Database)"],
                x["PERMIT_NUMBER"],
            ),
            fuzz.ratio(
                x["WaSC Supplementary Permit Ref.\n[optional]"],
                x["PERMIT_NUMBER"],
            ),
        ),
        axis=1,
    )
    distance_joined.reset_index(drop=True, inplace=True)

    # Filter out the rows with a score less than 92 because they aren't a good
    # enough match
    distance_joined.loc[distance_joined["score"] <= 92, "ID"] = np.nan

    # Keep the max score for each unique ID
    mask = distance_joined["score"] == distance_joined.groupby("Unique ID")[
        "score"
    ].transform("max")
    filtered = distance_joined[mask]

    # Remove duplicates and keep the first one
    filtered = filtered[
        ~((filtered["ID"].isna()) & (filtered.duplicated("Unique ID")))
    ]

    # Find the distance between the annual data and the consents
    filtered["distance"] = filtered.apply(
        lambda x: (
            x["OUTLET_LOC"].distance(x["geometry"])
            if x["OUTLET_LOC"] is not None
            else None
        ),
        axis=1,
    )

    # Keep on the the closest match for each unique ID
    dmask = filtered["distance"] == filtered.groupby("Unique ID")[
        "distance"
    ].transform("min")
    filtered = filtered[dmask]

    filtered.rename(
        columns={
            (
                "Total Duration (hh:mm:ss) all spills prior to processing "
                "through 12-24h count method"
            ): "SpillDuration"
        },
        inplace=True,
    )

    filtered = filtered[~filtered["Unique ID"].duplicated()]
    filtered = filtered.set_index(
        "Unique ID", drop=True, verify_integrity=True
    )
    filtered.drop(columns=["score", "distance", "OUTLET_LOC"], inplace=True)
    filtered2 = gpd.GeoDataFrame(filtered, geometry="geometry")
    return filtered2


def transform_data(
    annual: gpd.GeoDataFrame,
    consents: pd.DataFrame,
    determinands: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    """
    Transforms annual, consents, and determinands data.

    Parameters
    ----------
    annual : gpd.GeoDataFrame
        Annual CSO data.
    consents : pd.DataFrame
        Consents data.
    determinands : pd.DataFrame
        Determinands data.

    Returns
    -------
    tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]
        A tuple containing transformed CSOs, WwTWs, and determinands data.
    """
    wwtws, csos = split_consents(consents)
    determinands = determinands_transform(determinands)

    # Merge annual CSO data with consents
    csos_merged = merge_annual_and_consents(annual, csos)

    return csos_merged, wwtws, determinands


def get_data(
    repeat: bool = False,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """
    Retrieves CSO annual, consents, and determinands data.

    Parameters
    ----------
    repeat : bool, optional
        If True, forces redownload of data, by default False.

    Returns
    -------
    tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame]
        A tuple containing annual, consents, rivers and determinands data.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    annual = get_cso_annual_data(repeat)
    consents, determinands = get_consents_data(repeat)
    riversdf = get_rivers_data(repeat)
    return annual, consents, determinands, riversdf


def get_and_transform_data(
    repeat: bool = False,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """
    Retrieve and transform CSO annual, consents, and determinands data.

    Parameters
    ----------
    repeat : bool, optional
        If True, forces redownload and transformation of data, by default False.

    Returns
    -------
    tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame]
        A tuple containing transformed CSOs, WwTWs, rivers, and determinands data.
    """
    if (
        not os.path.exists(DATA_DIR.joinpath("cso.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("wwtw.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("determinands.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("rivers.geojson"))
        or repeat
    ):
        logger.info("Getting Data...")
        annual, consents, determinands, riversdf = get_data(repeat)
        logger.info("Data retrieved")
        logger.info("Transforming Data...")
        csos, wwtws, determinands = transform_data(
            annual, consents, determinands
        )
        logger.info("Data transformed")
        logger.info("Saving data...")
        csos.to_parquet(DATA_DIR.joinpath("cso.parquet"))
        wwtws.to_parquet(DATA_DIR.joinpath("wwtw.parquet"))
        determinands.to_parquet(DATA_DIR.joinpath("determinands.parquet"))
        logger.info("Data saved")
    else:
        logger.info("Loading downloaded and transformed data...")
        csos = gpd.read_parquet(DATA_DIR.joinpath("cso.parquet"))
        wwtws = gpd.read_parquet(DATA_DIR.joinpath("wwtw.parquet"))
        determinands = pd.read_parquet(
            DATA_DIR.joinpath("determinands.parquet")
        )
        riversdf = gpd.read_file(DATA_DIR.joinpath("rivers.geojson"))
        logger.info("Data loaded")
    return csos, wwtws, determinands, riversdf


if __name__ == "__main__":
    """
    Main entry point for the script. Retrieves, transforms, and saves data.
    """
    logger.info("Starting data processing...")
    try:
        _, _, _, _ = get_and_transform_data(True)
        logger.info("Data processing completed successfully.")
    except Exception as e:
        logger.critical(f"Data processing failed: {e}")
