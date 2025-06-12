# OpenRiskMap
A risk map generated for the Browney catchment with CSOs and Waste Water Treatment works:

![Output](./docs/output_browney.png)

---
## Table of Contents
  - [Motivation](#motivation)
  - [Project Details](#project-details)
  - [Installation](#installation)
    - [Additional Requirements](#additional-requirements)
  - [Directory Structure](#directory-structure)
  - [Usage](#usage)
    - [Choosing a Catchment](#choosing-a-catchment)
    - [Exploring the Data](#exploring-the-data)
    - [Re-running the Data Download and Transform (Optional)](#re-running-the-data-download-and-transform-optional)
  - [Implementation Details](#implementation-details)
    - [River Graph](#river-graph)
    - [Ingesting the Data](#ingesting-the-data)
      - [CSO Data](#cso-data)
      - [WwTW Data](#wwtw-data)
      - [Determinands Data](#determinands-data)
    - [Mapping Points to Rivers](#mapping-points-to-rivers)
    - [Calculating a Risk Value](#calculating-a-risk-value)
      - [River Flow Rate](#river-flow-rate)
      - [Active Phosphorus Load](#active-phosphorus-load)
      - [Risk Degradation](#risk-degradation)
      - [Phosphorus Risk](#phosphorus-risk)
  - [License](#license)
  - [Disclaimer](#disclaimer)

---

## Motivation

Water companies, catchment managers and other stakeholders face significant time and financial outgoings when attempting to design and implement water quality monitoring schemes within a catchment. Furthermore, it can be challenging to determine which sources of pollution represent the highest risk at different locations within a catchment, without prior water quality monitoring.

To address these challenges, River Deep Mountain AI is providing a standardised and open approach to produce catchment-wide 'risk maps', helping to highlight areas where pollutants (e.g. phosphorus) pose a higher threat to river water quality.
Our Open Risk Map can be used to inform where further on-the-ground walkovers may be needed and highlight the optimal locations for targeting investigations and monitoring.

## Project Details

River Deep Mountain AI is an innovation project funded by the Ofwat Innovation Fund working collaboratively to develop open-source AI/ML models that can inform effective actions to tackle waterbody pollution.

The project consists of 6 core partners: Northumbrian Water, Cognizant Ocean, Xylem Inc., Water Research Centre Limited, The Rivers Trust and ADAS. The project is further supported by 6 water companies across the United Kingdom and Ireland.

## Installation

This project uses Python(>3.7). Install the required dependencies (preferably in a new virtual environment) using:

```bash
$ pip install -r requirements.txt
```

### Additional Requirements

- **`mdb-export` Command**: Part of the [mdbtools](https://mdbtools.github.io/), required to process `.accdb` files into `.csv` format. This is necessary for re-downloading and extracting some datasets. Alternatively, the conversion can be done manually.
- This command is used to extract the EA Consents data from `.accdb` to `.csv` files. This can be done manually by converting them to `.csv`. The necessary tables and files are:
  - [determinands] -> `data/consentsdb/determinands.csv`
  - [consents_active] -> `data/consentsdb/consents.csv`
  - For doing this manually using MS Access:
    1. Download the file from [EA](https://environment.data.gov.uk/api/file/download?fileDataSetId=a54fdea1-7769-4b22-a518-10d51fed6f33&fileName=Consented%20Discharges%20to%20Controlled%20Waters%20with%20Conditions.zip) and extract it to the data folder
    2. Open MS Access, save the two tables as excel files. This will save them in `.xlsx` format. Then, open the files and save them as `CSV UTF-8` files with the names described above.

---

## Directory Structure

```
OpenRiskMap/
├── data/                     # Directory for storing downloaded and processed datasets
├── docs/                     # Directory for a more in depth documentation
├── get_and_transform_data.py # Script for downloading, transforming, and saving data
├── utils/                    # Utility functions for risk calculations
├── RiskMap/                  # Module for constructing and analyzing river risk maps
├── Exploration.ipynb         # Jupyter notebook for exploring and visualizing data
├── README.md                 # Project documentation
└── requirements.txt          # Python dependencies
```

---

## Usage

### Choosing a Catchment

By default, we have used the [Browney](https://environment.data.gov.uk/catchment-planning/OperationalCatchment/3052) catchment, as this is a catchment of special interest for Northumbrian Water, which leads RDMAI. However, the model has also been tested on other catchments. A different catchment for plotting can be chosen from the [catchment explorer](https://environment.data.gov.uk/catchment-planning) by copying the `.geojson` file URL and replacing the URL in the [`Exploration.ipynb`](./Exploration.ipynb) file with this URL.

### Exploring the Data

Use the [`Exploration.ipynb`](./Exploration.ipynb) notebook to visualise and analyse the data interactively. By running this notebook, missing data are also downloaded and transformed. Open the notebook in Jupyter:

```bash
$ jupyter notebook Exploration.ipynb
```

### Re-running the Data Download and Transform (Optional)

To download, transform, and save the required datasets from scratch, run the following command:

```bash
$ python get_and_transform_data.py
```

---

## Implementation Details

This is a high-level overview of the implementation details. For a more complete version, check the [Model Docs](docs/docs.md).

### River Graph

- **Source**: [Open River Network](https://openrivers.net/)
- **Structure**: The river network is represented as a directed graph composed of LineStrings. These are subdivided into nodes at a desired resolution using the `RiskMap` class.
- **Graph Construction**: The `RiskMap` class uses the `momepy` library to convert the river network into a primal graph. Each node represents a river segment intersection, and edges represent river segments.

### Ingesting the Data

#### CSO Data

- **Source**: [EA Storm Overflows - Annual Returns](https://environment.data.gov.uk/dataset/21e15f12-0df8-4bfc-b763-45226c16a8ac)
- **Details**: Each CSO has a unique ID and a Consent Permit Reference, which is matched to the EA Consents Database. The data are transformed into a GeoDataFrame with spatial information.

#### WwTW Data

- **Source**: [EA Consents Database](https://www.data.gov.uk/dataset/55b8eaa8-60df-48a8-929a-060891b7a109/consented-discharges-to-controlled-waters-with-conditions1)
- **Details**: Filtered to include only WwTWs based on specific columns in the database. The data are transformed into a GeoDataFrame with spatial information.

#### Determinands Data

- **Details**: Determinands data are processed to extract relevant information such as phosphorus levels and flow rates. The data are cleaned and transformed for use in risk calculations.

### Mapping Points to Rivers

- **Tolerance**: Points are mapped to the closest river within a 700 m tolerance.
- **Method**: The `RiskMap.add_point_info_to_map` method identifies the closest point on the river for each outflow location and propagates this information along the river network.

### Calculating a Risk Value

#### River Flow Rate

- **Approximation**: Linear regression using upstream accumulated length for Q50 flow.
- **Correlation**: $R^2 \sim 0.7$ with upstream accumulated length.

#### Active Phosphorus Load

- **CSOs**: Estimated using spill duration and default phosphorus concentration.
- **WwTWs**: Derived from consented phosphorus values and Dry Water Flow (DWF).

#### Risk Degradation

- **Model**: Exponential decay based on flow velocity and phosphorus degradation rate.

#### Phosphorus Risk

- **Formula**: Risk is calculated as a percentage of the UKTAG Revised Standards for poor river health:
  $$Risk = \frac{C_P}{C_{UKTAG}(0.87mg/l)} \times 100$$
- **Aggregation**: Risk values are aggregated using weighted averages or sums, depending on the use case.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

River Deep Mountain AI (“RDMAI”) is run by a collection of UK water companies and their technology partners. The entities currently participating in RDMAI are listed at the end of this section and they are collectively referred to in these terms as the “consortium”.

This section provides additional context and usage guidance specific to the artificial intelligence models and / or software (the “**Software**”) distributed under the MIT License. It does not modify or override the terms of the MIT License.  In the event of any conflict between this section and the terms of the MIT licence, the terms of the MIT licence shall take precedence.

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
 
1. Anglian Water Services Limited 
2. Southwest Water Limited 
3. Northern Ireland Water 
4. Wessex Water Limited
5. The Rivers Trust
6. RSK ADAS Limited
7. Water Research Centre Limited
8. Xylem
9. Northumbrian Water Limited
10. Cognizant Worldwide Limited
---