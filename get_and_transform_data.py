import io
import logging
import os
import pathlib
import subprocess
import zipfile

import fiona
import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely
from fuzzywuzzy import fuzz
from OSGridConverter import grid2latlong

# Configure logger
logger = logging.getLogger(__name__)

DATA_DIR: pathlib.Path = pathlib.Path(
    os.path.relpath(
        pathlib.Path(__file__).parent.joinpath("data"),
        pathlib.Path.cwd(),
    )
)
OUTPUT_EPSG: int = 27700


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
        ngrs = (
            annual["Outlet Discharge NGR\n(EA Consents Database)"]
            .str.split(" ")
            .str[0]
            .str.split(",")
            .str[0]
        )
        annual["geometry"] = ngrs.map(get_lat_lon)

        annual = gpd.GeoDataFrame(
            annual, geometry="geometry", crs="EPSG:4326"
        ).to_crs(epsg=OUTPUT_EPSG)

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
    consents_path = consentsdb_path.joinpath("consents.csv")
    det_path = consentsdb_path.joinpath("determinands.csv")

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
    if os.path.exists(DATA_DIR.joinpath("rivers.parquet")) and not repeat:
        logger.info("Rivers data found")
        return gpd.read_parquet(DATA_DIR.joinpath("rivers.parquet"))
    logger.info("Downloading rivers data...")

    header = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
    } # For spoofing browser user agent

    try:
        req = requests.get(
            "https://openrivers.net/download/ORN_v2_GeoPackage.zip",
            headers=header,
            allow_redirects=True,
            timeout=1000,
        )
    except Exception as e:
        logger.error(
            f"Failed to download or transform rivers data: {e}, trying alternate method"
        )
        try:
            req = requests.get(
                "https://openrivers.net/download/ORN_v2_GeoPackage.zip",
                headers=header,
                allow_redirects=True,
                timeout=1000,
                verify=False,
            )
        except Exception as e:
            logger.error(f"Alternate method failed: {e}")
            raise e
    b = bytes(req.content)
    with fiona.BytesCollection(b, layer="ORN") as f:
        crs = f.crs
        rivers = gpd.GeoDataFrame.from_features(f, crs=crs)
    rivers = rivers.to_crs(epsg=OUTPUT_EPSG)
    rivers.to_parquet(DATA_DIR.joinpath("rivers.parquet"))
    logger.info("Rivers data downloaded and transformed")
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
        ID=(
            df["PERMIT_NUMBER"].astype(str)
            + "_"
            + df["EFFLUENT_NUMBER"].astype(str)
            + "_"
            + df["OUTLET_NUMBER"].astype(str)
        )
    )

    df.set_index("ID", inplace=True)
    df = df.assign(OUTLET_LOC=df["OUTLET_GRID_REF"].map(get_lat_lon))
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
        (
            (consents["DISCHARGE_SITE_TYPE_CODE"] == "A2")
            & (consents["EFFLUENT_TYPE"] == "SA")
            & (
                (consents["OUTLET_TYPE_CODE"] == "S")
                | (consents["OUTLET_TYPE_CODE"] == "U")
            )
        )  # Including the water company treatment works
        | (
            consents["DISCHARGE_SITE_TYPE_CODE"].isin(["A0", "A1"])
        )  # Including the private treatment works
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


def get_OS_data(repeat: bool = False):
    """
    This function queries the Ordinance survey Local Map and Built Up Areas
    datasets and downloads them if they are not already present in the data
    directory.

    Parameters
    ----------
    repeat : bool, optional
        If True, forces redownload of data, by default False
    """
    if (
        os.path.exists(DATA_DIR.joinpath("os_roads.parquet"))
        and os.path.exists(DATA_DIR.joinpath("os_buildings.parquet"))
        and os.path.exists(DATA_DIR.joinpath("os_builtup.parquet"))
        and not repeat
    ):
        logger.info("OS data found")
        return

    logger.info("Downloading OS data...")
    BUILT_UP_AREAS_URL = "https://api.os.uk/downloads/v1/products/BuiltUpAreas/downloads?area=GB&format=GeoPackage&redirect"
    BUILT_UP_ZIP_PATH = DATA_DIR.joinpath("built_up_areas.zip")
    r = requests.get(
        BUILT_UP_AREAS_URL,
        allow_redirects=True,
        timeout=1000,
    )
    with open(BUILT_UP_ZIP_PATH, "wb") as f:
        f.write(r.content)

    with zipfile.ZipFile(BUILT_UP_ZIP_PATH, "r") as z:
        z.extract("os_open_built_up_areas.gpkg", DATA_DIR)
    builtup = gpd.read_file(
        DATA_DIR.joinpath("os_open_built_up_areas.gpkg"),
        layer="os_open_built_up_areas",
    ).to_crs(epsg=OUTPUT_EPSG)[["geometry"]]
    builtup.to_parquet(DATA_DIR.joinpath("os_builtup.parquet"))

    OS_LOCAL_MAP_URL = "https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads?area=GB&format=GeoPackage&redirect"
    OS_LOCAL_ZIP_PATH = DATA_DIR.joinpath("os_local_map.zip")
    r = requests.get(
        OS_LOCAL_MAP_URL,
        allow_redirects=True,
        timeout=10000,
    )
    with open(OS_LOCAL_ZIP_PATH, "wb") as f:
        f.write(r.content)
    with zipfile.ZipFile(OS_LOCAL_ZIP_PATH, "r") as z:
        z.extract("Data/opmplc_gb.gpkg", DATA_DIR)
    os.rename(
        DATA_DIR.joinpath("Data", "opmplc_gb.gpkg"),
        DATA_DIR.joinpath("opmplc_gb.gpkg"),
    )
    roads = gpd.read_file(
        DATA_DIR.joinpath("opmplc_gb.gpkg"),
        layer="road",
        use_arrow=True,
    ).to_crs(epsg=OUTPUT_EPSG)
    roads.to_parquet(
        DATA_DIR.joinpath("os_roads.parquet"), write_covering_bbox=True
    )
    buildings = gpd.read_file(
        DATA_DIR.joinpath("opmplc_gb.gpkg"),
        layer="building",
        use_arrow=True,
    ).to_crs(epsg=OUTPUT_EPSG)[["geometry"]]
    buildings.to_parquet(
        DATA_DIR.joinpath("os_buildings.parquet"), write_covering_bbox=True
    )

    # Remove unneeded files
    os.remove(DATA_DIR.joinpath("os_open_built_up_areas.gpkg"))
    os.remove(BUILT_UP_ZIP_PATH)
    os.rmdir(DATA_DIR.joinpath("Data"))
    os.remove(OS_LOCAL_ZIP_PATH)
    os.remove(DATA_DIR.joinpath("opmplc_gb.gpkg"))
    logger.info("OS data downloaded and saved")
    return


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
    get_OS_data(repeat)
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
        or not os.path.exists(DATA_DIR.joinpath("rivers.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("os_roads.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("os_buildings.parquet"))
        or not os.path.exists(DATA_DIR.joinpath("os_builtup.parquet"))
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
        riversdf = gpd.read_parquet(DATA_DIR.joinpath("rivers.parquet"))
        logger.info("Data loaded")
    return csos, wwtws, determinands, riversdf


def get_crome_data(
    mask: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    This function is meant to retrieve the Crop Map of England data
    for the area defined by the mask.

    Args:
        mask (gpd.GeoDataFrame): A GeoDataFrame defining the area of interest.

    Returns:
        gpd.GeoDataFrame: A GeoDataframe with Crop category information
    """
    bbox = mask.to_crs(epsg=4326).total_bounds
    bbox_str = (
        f"{bbox[0]-0.0005},{bbox[1]-0.0005},{bbox[2]+0.0005},{bbox[3]+0.0005}"
    )
    crome = gpd.read_file(
        r"https://environment.data.gov.uk/geoservices/datasets/"
        r"a27312b5-d6c9-4710-ad5e-382d727c1b05/ogc/features/v1/collections"
        r"/Crop_Map_of_England_2023/items?f=application%2Fgeo%2Bjson"
        f"&bbox={bbox_str}&limit=1000000000",
        mask=mask.to_crs(epsg=4326),
    )
    if mask.crs is not None:
        crome = crome.to_crs(mask.crs)
    crop_categories = pd.read_csv(
        DATA_DIR.joinpath("crop_categories.csv"), index_col=0
    )
    crop_categories = crop_categories[crop_categories["category"] != "N/A"]
    crome_cats = crome.join(
        crop_categories[["crop_category"]],
        on="lucode",
        how="left",
        validate="m:1",
    )
    return crome_cats


def get_soil_data() -> gpd.GeoDataFrame:
    """
    Retrieves and transforms soil host data.

    Returns:
        gpd.GeoDataFrame: A GeoDataFrame with soil host data and categories.
    """
    soil_host = gpd.read_file(DATA_DIR.joinpath("soil_host_data.zip")).to_crs(
        epsg=27700
    )[["HOST", "geometry"]]

    host_lookup = pd.read_csv(
        DATA_DIR.joinpath("soil_lookup.csv"), index_col=0
    )

    soil_cats = soil_host.join(
        host_lookup,
        on="HOST",
        how="left",
        validate="m:1",
    )
    return soil_cats


def get_rainfall_data() -> gpd.GeoDataFrame:
    """
    Retrieves and transforms annual average rainfall data.

    Returns:
        gpd.GeoDataFrame: Returns the class of the rainfall
        based on the annual average rainfall.
    """

    rainfall = gpd.read_file(
        "https://services.arcgis.com/Lq3V5RFuTBC9I7kv/"
        "arcgis/rest/services/Annual_Precipitation_Observations"
        "_1991_2020/FeatureServer/replicafilescache/"
        "Annual_Precipitation_Observations_1991_2020"
        "_3705384685436209699.geojson"
    ).to_crs(epsg=27700)

    def classify_rainfall(value):
        if value > 1500:
            return 5
        elif value > 1200:
            return 4
        elif value > 900:
            return 3
        elif value > 700:
            return 2
        elif value > 600:
            return 1
        else:
            return 0

    rainfall["rainfall_category"] = rainfall["pr"].apply(classify_rainfall)
    return rainfall


def get_land_cover_data(mask: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Retrieves and transforms land cover data for the area defined by the mask.

    Args:
        mask (gpd.GeoDataFrame): A GeoDataFrame defining the area of interest.

    Returns:
        gpd.GeoDataFrame: A GeoDataFrame with land cover data
    """
    logger.info("Obtaining land cover data...")
    crome = get_crome_data(mask)
    soil = get_soil_data()
    rain = get_rainfall_data()
    logger.info("Obtained the data")
    combined = gpd.overlay(
        crome,
        soil[["geometry", "soil_category"]],
        how="intersection",
    )
    final_combined = gpd.overlay(
        combined,
        rain[["geometry", "rainfall_category"]],
        how="intersection",
    )
    logger.info("Land cover data transformed")
    return final_combined


if __name__ == "__main__":
    """
    Main entry point for the script. Retrieves, transforms, and saves data.
    """
    logger.info("Starting data processing...")
    try:
        _, _, _, _ = get_and_transform_data(True)
        get_OS_data(True)
        logger.info("Data processing completed successfully.")
    except Exception as e:
        logger.critical(f"Data processing failed: {e}")
