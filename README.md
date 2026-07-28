# A Spatio-Temporal Dataset of Court-Adjudicated Traffic Accident Cases in China (2000-2020)

This repository contains the data-processing and analysis code associated with the construction of a nationwide dataset of court-adjudicated traffic-accident cases in China.

## Overview

China does not currently provide a unified, nationwide, long-term, record-level traffic-accident dataset with consistently available temporal and location information. This project uses an indirect data-construction strategy based on publicly available court judgment documents. Large language models are used to extract structured accident information from unstructured judicial text, and geocoding is used to derive standardized spatial coordinates.

Starting from 85,112,456 collected court judgment documents, the workflow retained 3,298,640 documents for large-language-model extraction and ultimately produced 1,400,705 first-instance civil and criminal judgment records. The final dataset covers accident occurrence years 2000-2020 and includes records from 34 provincial-level regions, 370 municipal-level regions, and 2,832 county/district-level jurisdictions.

The dataset is a collection of cases that entered the judicial process. It is not a census of all traffic accidents in China and should not be used to estimate absolute accident frequency or population-level accident risk without accounting for selection, exposure, litigation, and court-document disclosure mechanisms.

## Data access

The dataset is not stored in this code repository. Download the released CSV data from Figshare:

**https://doi.org/10.6084/m9.figshare.31829782**

The released dataset is available under the Creative Commons Attribution 4.0 International license (CC BY 4.0). Please cite the Figshare record and the associated paper when using the data.

## Dataset fields

| Field | Description |
| --- | --- |
| `case_number` | Unique case identifier |
| `court_name` | Name of the adjudicating court |
| `privy` | Parties involved in the case; names may be anonymized |
| `case_text` | Original judicial text |
| `case_dt_hour` | Standardized accident occurrence time at hourly resolution |
| `province` | Province-level administrative region |
| `city` | Municipality or prefecture-level city |
| `district` | County or urban district |
| `specific_place` | Text description of the accident location |
| `lng` | WGS84 longitude |
| `lat` | WGS84 latitude |
| `vehicle` | Vehicle category: 0 = car only; 1 = car vs. motorcycle/e-bike; 2 = car vs. pedestrian; 3 = motorcycle/e-bike vs. pedestrian |
| `death` | Fatality outcome: 0 = no fatality; 1 = at least one fatality |

## Processing workflow

The numeric filename prefixes indicate the intended processing order.

| Stage | Main files | Purpose |
| --- | --- | --- |
| 1. Source screening | `1.1 fillter_data_develop.ipynb`, `1.2 fillter_data_main.ipynb`, `1.3 count line.ipynb` | Explore, filter, batch-process, merge, and count court judgment records |
| 2. LLM extraction | `2.1 llm_test.py`, `2.2 llm.ipynb`, `2.3 zetatechs_transport.py` | Test an OpenAI-compatible endpoint and extract accident time, location, vehicle, and fatality fields; the batch script supports resumption |
| 3. Cleaning and standardization | `3.1 filter_result.ipynb`, `3.2 Address geocoding.ipynb`, `3.2 bd092wgs84.py`, `3.2 gb18030_utf-8-sig.py`, `3.3 time_calculation.ipynb`, `3.4 combin_csv.ipynb` | Clean extracted locations, geocode addresses, convert coordinates to WGS84, normalize encodings and time, and combine outputs |
| 4. Analysis and visualization | `4.1 geo_visualization.ipynb` through `4.6 city_analysis.ipynb` | Produce temporal, geographic, vehicle-type, fatality, and accident-to-judgment analyses |
| 5. Dataset assembly | `5.1 output_dataset.ipynb`, `5.2fillter_first.ipynb` | Assemble the release fields and retain first-instance civil and criminal judgments |

The extraction used Google Gemini 2.0 Flash (`gemini-2.0-flash-001`) through an OpenAI-compatible API with temperature set to 0 and JSON-constrained responses. Address descriptions were geocoded with the Baidu Maps API and converted to WGS84 coordinates.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Some geospatial dependencies, particularly GeoPandas and Cartopy, may require platform-specific native libraries. A Conda or Mamba environment can be easier to use when binary wheels are unavailable.

## API configuration

Do not place API credentials directly in scripts or notebooks. Set the required environment variables before running the LLM extraction or geocoding steps:

```bash
export LLM_API_KEY="your-openai-compatible-api-key"
export BAIDU_MAP_AK="your-baidu-maps-ak"
```

The example values in `.env.example` are intentionally empty and are not loaded automatically. Export the variables in your shell or adapt the code to your preferred secrets manager.

## Input paths

The scripts retain the relative directory structure used during dataset construction and generally expect intermediate data under a sibling `../data/` directory. After downloading data, update the paths in each notebook to match your local layout. The complete raw judgment corpus and every intermediate processing file are not included in this repository or necessarily in the Figshare release.

A typical local layout is:

```text
project/
├── Traffic-Accident-Code/   # this repository
└── data/                    # downloaded or locally generated inputs
```

Run notebooks interactively and inspect each input/output path before processing the full dataset. The geocoding and LLM steps call paid or rate-limited external services, so test them on a small sample first.

## Scope and appropriate use

Suitable uses include:

- descriptive spatial coverage and hotspot exploration;
- temporal-pattern analysis of included court-adjudicated cases;
- analysis of accident-to-judgment intervals and judicial processing;
- linkage with road networks, built-environment, population, or economic data.

The dataset is not suitable for:

- estimating the total number or absolute probability of all traffic accidents in a region;
- treating annual record counts as national accident trends;
- microscopic analysis of minor collisions that did not enter the judicial process;
- causal or regional-risk comparisons without appropriate exposure variables and selection-bias controls.

## Authors

Lei Wang, Rui Yue, and Fan Zhang.

## Citation

When using this repository or dataset, cite the associated paper:

> Wang, L., Yue, R. & Zhang, F. *A Spatio-Temporal Dataset of Court-Adjudicated Traffic Accident Cases in China (2000-2020).*

Also cite the dataset record: https://doi.org/10.6084/m9.figshare.31829782
