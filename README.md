# Open Risk Map

A risk map generated for the [Browney catchment](https://environment.data.gov.uk/catchment-planning/OperationalCatchment/3052)($1819\  ha$, Northumberland) with locations of combined sewer overflows (CSOs) and wastewater treatment works (WwTWs) is shown below:

![Output](./docs/images/output_browney.png)

---

## Table of Contents

- [Open Risk Map](#open-risk-map)
  - [Table of Contents](#table-of-contents)
  - [Motivation](#motivation)
  - [Project Details](#project-details)
  - [Installation](#installation)
  - [Directory Structure](#directory-structure)
  - [Usage](#usage)
    - [Choosing a Catchment](#choosing-a-catchment)
    - [Exploring the Data](#exploring-the-data)
    - [Re-running the Data Download and Transform (Optional)](#re-running-the-data-download-and-transform-optional)
  - [Implementation Details](#implementation-details)
    - [Data Sources](#data-sources)
    - [Mapping points to rivers (Point sources)](#mapping-points-to-rivers-point-sources)
    - [Mapping subcatchments to rivers (Diffuse sources)](#mapping-subcatchments-to-rivers-diffuse-sources)
    - [Calculating a Risk Value](#calculating-a-risk-value)
      - [River Flow Rate](#river-flow-rate)
      - [Load](#load)
      - [Pollutant Degradation](#pollutant-degradation)
      - [Risk](#risk)
  - [License](#license)
  - [Disclaimer](#disclaimer)
    - [1. Research and Development Status](#1-research-and-development-status)
    - [2. Software Knowledge Cutoff](#2-software-knowledge-cutoff)
    - [3. Experimental and Generative Nature](#3-experimental-and-generative-nature)
    - [4. Usage Considerations](#4-usage-considerations)
    - [5. No Liability](#5-no-liability)
    - [6. Consortium Members](#6-consortium-members)

---

## Motivation

Water companies, catchment managers and other stakeholders face significant time and financial outgoings when attempting to design and implement water quality monitoring schemes within a catchment. Furthermore, it can be challenging to determine which sources of pollution represent the highest risk at different locations within a catchment, without prior water quality monitoring.

To address these challenges, River Deep Mountain AI is providing a standardised and open approach to produce catchment-wide 'risk maps', helping to highlight areas where pollutants (e.g. phosphorus) pose a higher threat to river water quality.
Our Open Risk Map can be used to inform where further on-the-ground walkovers may be needed and highlight the optimal locations for targeting investigations and monitoring.

## Project Details

River Deep Mountain AI is an innovation project funded by the Ofwat Innovation Fund working collaboratively to develop open-source AI/ML models that can inform effective actions to tackle waterbody pollution.

The project consists of 6 core partners: Northumbrian Water, Cognizant Ocean, Xylem Inc., Water Research Centre Limited, The Rivers Trust and ADAS. The project is further supported by 6 water companies across the United Kingdom and Ireland.


### Report Download
Please download the Open Risk Map Report [HERE](https://github.com/Cognizant-RDMAI/Open-Risk-Map/tree/main/docs).

### Benchmark Download:

River Deep Mountain AI models have been independently benchmarked by WRc and ADAS, against existing industry-standard tools. The benchmarking reports assess model performance, ‘ease-of-use’, time and cost requirements.Read the full report [here](https://github.com/Cognizant-RDMAI/Open-Risk-Map/tree/main/docs).

### Whitepaper Download:

Please download the whitepaper [here](https://github.com/Cognizant-RDMAI/Open-Risk-Map/tree/main/docs).

## Installation

This project uses Python(>3.7). Install the required dependencies (preferably in a new virtual environment) using:

```bash
pip install -r requirements.txt
```

There are some additional steps that need to be followed to ensure smooth operation:

- **`mdb-export` Command**: Part of the [mdbtools](https://mdbtools.github.io/), required to process `.accdb` files into `.csv` format. This is necessary for re-downloading and extracting some datasets. Alternatively, the conversion can be done manually.
  - This command is used to extract the EA Consents data from `.accdb` to `.csv` files. This can be done manually by converting them to `.csv`. The necessary tables and files are:
    - [determinands] -> `data/consentsdb/determinands.csv`
    - [consents_active] -> `data/consentsdb/consents.csv`
    - For doing this manually using MS Access:
      1. Download the file from [EA](https://environment.data.gov.uk/api/file/download?fileDataSetId=a54fdea1-7769-4b22-a518-10d51fed6f33&fileName=Consented%20Discharges%20to%20Controlled%20Waters%20with%20Conditions.zip) and extract it to the data folder
      2. Open MS Access, save the two tables as excel files. This will save them in `.xlsx` format. Then, open the files and save them as `CSV UTF-8` files with the names described above.
- In the case you're using Windows, you might need to clone the repository in a directory with a smaller path. This is due to a [quirk of windows](https://learn.microsoft.com/en-us/answers/questions/3279782/how-can-i-fix-error-0x80010135-path-too-long) where unzipping files in directories with long paths can cause issues.

---

## Directory Structure

```bash
└──main/
    ├── CONTRIBUTING.md                  # Contributor Guidelines
    ├── Exploration.ipynb                # Notebook to explore the data and generate risk maps
    ├── LICENSE                          # License information
    ├── README.md                        # This file
    ├── RiskMap.py                       # Main class to generate risk maps
    ├── data                             # Directory to store all the data
    │   └── ...
    ├── docs                             # Documentation
    │   ├── docs.md                      # Documentation file
    │   └── images                       # Images for the documentation
    │       └── ...
    ├── get_and_transform_data.py        # Script to download and transform all the data
    ├── pollutant_parameters             # Directory to store pollutant parameters
    │   └── ...
    ├── requirements.txt                 # Python dependencies
    └── utils                            # Utility scripts
        └── ...
```

---

## Usage

### Choosing a Catchment

By default, the [Browney](https://environment.data.gov.uk/catchment-planning/OperationalCatchment/3052) catchment is used, as this is a catchment of special interest for Northumbrian Water, which leads RDMAI. However, the model has also been tested on other catchments. A different catchment for plotting can be chosen from the [catchment explorer](https://environment.data.gov.uk/catchment-planning) by copying the `.geojson` file URL and replacing the URL in the [`Exploration.ipynb`](./Exploration.ipynb) file with this URL.

### Exploring the Data

Use the [`Exploration.ipynb`](./Exploration.ipynb) notebook to visualise and analyse the data interactively. By running this notebook, missing data are also downloaded and transformed.

### Re-running the Data Download and Transform (Optional)

To download, transform, and save the required datasets from scratch, run the following command:

```bash
python get_and_transform_data.py
```

---

## Implementation Details

This is a high-level overview of the implementation details. For a more complete version, check the [Model Docs](docs/docs.md).

### Data Sources

This project integrates multiple open datasets to generate risk maps:

- **Rivers**: [Open River Network](https://openrivers.net/) provides the river network as LineStrings, used to build a directed graph of river reaches.
- **Overflow Data**: [EA Storm Overflows - Annual Returns](https://environment.data.gov.uk/dataset/21e15f12-0df8-4bfc-b763-45226c16a8ac) supplies annual returns for storm overflows, matched to consents data.
- **Consents Data**: [EA Consents Database](https://www.data.gov.uk/dataset/55b8eaa8-60df-48a8-929a-060891b7a109/consented-discharges-to-controlled-waters-with-conditions1) contains permit conditions and locations for WwTWs and overflows.
- **Land Use Data**: [CROME 2023](https://environment.data.gov.uk/dataset/a27312b5-d6c9-4710-ad5e-382d727c1b05) provides crop and land use information, joined with lookup tables for risk estimation.
- **Soil Data**: Open HOST dataset (derived from SGDBE) is used for hydrology of soil types, stored in `data/soil_host_data.zip`.
- **Rainfall Data**: [UK Met Office Rainfall Data](https://www.arcgis.com/home/item.html?id=f6ed302049894ee8b230215a3efa9c19) gives annual rainfall on a 12x12km grid.
- **Topography Data**: Elevation data is obtained via the [elevatr](https://github.com/titouanlegourrierec/elevatr) library for catchment delineation.
- **Ordnance Survey Data**: [OS OpenMap - Local](https://www.ordnancesurvey.co.uk/products/os-open-map-local) and [OS Open Built Up Areas](https://www.ordnancesurvey.co.uk/products/os-open-built-up-areas) provide roads, buildings, and urban area extents for urban runoff calculations.
- **Farmscoper Data**: [ADAS Farmscoper Tool](https://adas.co.uk/services/farmscoper/) is used for agricultural and livestock runoff estimates via lookup tables.

All data download and transformation is handled by [`get_and_transform_data.py`](./get_and_transform_data.py) and stored in the [`data/`](./data/) directory.

### Mapping points to rivers (Point sources)

- **Method**: The [`RiskMap.add_point_info_to_map`](./RiskMap.py) method identifies the closest point on the river for each outflow location and propagates this information along the river network.
- **Tolerance**: Points are mapped to the closest river within a 700 m tolerance.

### Mapping subcatchments to rivers (Diffuse sources)

- **Method**: The [`utils/catchment_delineation.py`](./utils/catchment_delineation.py) script delineates subcatchments using elevation data and the [whitebox-workflows](https://www.whiteboxgeo.com/whitebox-workflows-for-python/) library.
- **Tolerance**: Subcatchments smaller than $20,000 m^2$ (2 ha) are joined to their nearest downstream subcatchment to avoid very small areas that may skew results.
- These subcatchments are then used to map back diffuse pollution to the point in the river network using the [`RiskMap.add_subcatchment_info_to_map`](./RiskMap.py) method.

### Calculating a Risk Value

#### River Flow Rate

- **Approximation**: Linear regression using upstream accumulated length for Q50 flow.
- **Correlation**: $R^2 \sim 0.7$ with upstream accumulated length.

#### Load

- **CSOs**: Estimated using spill duration and default pollutant concentration.
- **WwTWs**: Derived from consented pollutant values and Dry Water Flow (DWF).
- **Land Use**: Obtained from the [farmscoper tool](https://adas.co.uk/services/farmscoper/)
- **Urban Runoff**: Calculated using total area and rainfall to estimate volume, and event mean concentration (EMC) values from literature to estimate the load in that volume of runoff.

#### Pollutant Degradation

- Exponential decay based on flow velocity and the degradation rates of the pollutants.

#### Risk

- **Formula**: Risk is calculated as a percentage of the standard for poor river health for that pollutant:

  $$Risk = \frac{c_{pollutant}}{c_{standard}} \times 100$$
  - For Phosphorus, the UKTAG Revised Standard for poor river health is $0.87 mg/l$.
  - For Ammoniacal Nitrogen, the 99th percentile WFD in the poor category is $6.0 mg/l$.

- **Aggregation**: Risk values are aggregated as the mean by default, but can be substituted with any function as per the use case.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

River Deep Mountain AI (“RDMAI”) consists of 10 parties. The parties currently participating in RDMAI are listed at the end of this section and they are collectively referred to in these terms as the “consortium”.

This section provides additional context and usage guidance specific to the artificial intelligence models and / or software (the “**Software**”) distributed under the MIT License. It does not modify or override the terms of the MIT License. In the event of any conflict between this section and the terms of the MIT licence, the terms of the MIT licence shall take precedence.

### 1. Research and Development Status

The Software has been created as part of a research and development project and reflects a point-in-time snapshot of an evolving project. It is provided without any warranty, representation or commitment of any kind including with regards to title, non-infringement, accuracy, completeness, or performance. The Software is for information purposes only and it is not: (1) intended for production use unless the user accepts full liability for its use of the Software and independently validates that the Software is appropriate for its required use; and / or (2) intended to be the basis of making any decision without independent validation. No party, including any member of the development consortium, is obligated to provide updates, maintenance, or support in relation to the Software and / or any associated documentation.

### 2. Software Knowledge Cutoff

The Software was trained on publicly available data up to January 2025. It may not reflect current scientific understanding, environmental conditions, or regulatory standards. Users are solely responsible for verifying the accuracy, timeliness, and applicability of any outputs.

### 3. Experimental and Generative Nature

The Software may exhibit limitations, including but not limited to:

- Inaccurate, incomplete, or misleading outputs;
- Embedded biases and / or assumptions in training data;
- Non-deterministic and / or unexpected behaviour;
- Limited transparency in model logic or decision-making

Users must critically evaluate and independently validate all outputs and exercise independent scientific, legal, and technical judgment when using the Software and / or any outputs. The Software is not a substitute for professional expertise and / or regulatory compliance.

### 4. Usage Considerations

- Bias and Fairness: The Software may reflect biases present in its training data. Users are responsible for identifying and mitigating such biases in their applications.
- Ethical and Lawful Use: The Software is intended solely for lawful, ethical, and development purposes. It must not be used in any way that could result in harm to individuals, communities, and / or the environment, or in any way that violates applicable laws and / or regulations.
- Data Privacy: The Software was trained on publicly available datasets. Users must ensure compliance with all applicable data privacy laws and licensing terms when using the Software in any way.
- Environmental and Regulatory Risk: Users are not permitted to use the Software for environmental monitoring, regulatory reporting, or decision making in relation to public health, public policy and / or commercial matters. Any such use is in violation of these terms and at the user’s sole risk and discretion.

### 5. No Liability

This section is intended to clarify, and not to limit or modify, the disclaimer of warranties and limitation of liability already provided under the MIT License.

To the extent permitted by applicable law, users acknowledge and agree that:

- The Software is not permitted for use in environmental monitoring, regulatory compliance, or decision making in relation to public health, public policy and / or commercial matters.
- Any use of the Software in such contexts is in violation of these terms and undertaken entirely at the user’s own risk.
- The development consortium and all consortium members, contributors and their affiliates expressly disclaim any responsibility or liability for any use of the Software including (but not limited to):
  - Environmental, ecological, public health, public policy or commercial outcomes
  - Regulatory and / or legal compliance failures
  - Misinterpretation, misuse, or reliance on the Software’s outputs
  - Any direct, indirect, incidental, or consequential damages arising from use of the Software including (but not limited to) any (1) loss of profit, (2) loss of use, (3) loss of income, (4) loss of production or accruals, (5) loss of anticipated savings, (6) loss of business or contracts, (7) loss or depletion of goodwill, (8) loss of goods, (9) loss or corruption of data, information, or software, (10) pure economic loss, or (11) wasted expenditure resulting from use of the Software —whether arising in contract, tort, or otherwise, even if foreseeable .

Users assume full responsibility for their use of the Software, validating the Software’s outputs and for any decisions and / or actions taken based on their use of the Software and / or its outputs.

### 6. Consortium Members

1. Northumbrian Water Limited
2. Cognizant Worldwide Limited
3. Xylem Water Solutions UK Limited
4. Water Research Centre Limited
5. RSK ADAS Limited
6. The Rivers Trust
7. Wessex Water Limited
8. Northern Ireland Water
9. Southwest Water Limited
10. Anglian Water Services Limited

---
