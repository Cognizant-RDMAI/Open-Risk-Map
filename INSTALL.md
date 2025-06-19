# Installation

This project uses Python(>3.7). Install the required dependencies (preferably in a new virtual environment) using:

```bash
$ pip install -r requirements.txt
```

## Additional Requirements

- **`mdb-export` Command**: Part of the [mdbtools](https://mdbtools.github.io/), required to process `.accdb` files into `.csv` format. This is necessary for re-downloading and extracting some datasets. Alternatively, the conversion can be done manually.
- This command is used to extract the EA Consents data from `.accdb` to `.csv` files. This can be done manually by converting them to `.csv`. The necessary tables and files are:
  - [determinands] -> `data/consentsdb/determinands.csv`
  - [consents_active] -> `data/consentsdb/consents.csv`
  - For doing this manually using MS Access:
    1. Download the file from [EA](https://environment.data.gov.uk/api/file/download?fileDataSetId=a54fdea1-7769-4b22-a518-10d51fed6f33&fileName=Consented%20Discharges%20to%20Controlled%20Waters%20with%20Conditions.zip) and extract it to the data folder
    2. Open MS Access, save the two tables as excel files. This will save them in `.xlsx` format. Then open the files and save them as `CSV UTF-8` files with the names described above.
