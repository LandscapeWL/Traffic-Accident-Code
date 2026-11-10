# A Spatio-Temporal Dataset of Court-Adjudicated Traffic Accident Cases in China (2000-2020)

This repository contains the data-processing and analysis code associated with the construction of a nationwide dataset of court-adjudicated traffic-accident cases in China.

## Overview

China does not currently provide a unified, nationwide, long-term, record-level traffic-accident dataset with consistently available temporal and location information. This project uses an indirect data-construction strategy based on publicly available court judgment documents. Large language models are used to extract structured accident information from unstructured judicial text, and geocoding is used to derive standardized spatial coordinates.

Starting from 85,057,901 collected court judgment documents, the workflow retained 3,298,640 documents for large-language-model extraction and ultimately produced 1,364,294 first-instance civil and criminal judgment records. These counts follow the revised manuscript supplied with the November 2026 code update; they have not been recomputed from the raw corpus in this repository. The manuscript concerns accident occurrence years 2000–2020. Individual analysis scripts apply their own inclusion filters, described below.

The dataset is a collection of cases that entered the judicial process. It is not a census of all traffic accidents in China and should not be used to estimate absolute accident frequency or population-level accident risk without accounting for selection, exposure, litigation, and court-document disclosure mechanisms.

## Data access

The dataset is not stored in this code repository. Download the released CSV data from Figshare:

**https://doi.org/10.6084/m9.figshare.31829782**

Check the Figshare record for the available dataset version and its license. Updating this code repository does not update the Figshare files. Please cite the Figshare record and the associated paper when using the data.

## Revised screening counts

| Step | Retained records |
| --- | ---: |
| Collected judgments | 85,057,901 |
| Cause-of-action and full-text screening | 3,298,640 |
| Location screening; submitted for geocoding | 1,831,978 |
| Original hourly time eligibility | 1,577,538 |
| Record-level deduplication (41,563 removed) | 1,535,975 |
| First-instance civil/criminal judgments (171,681 removed) | 1,364,294 |

Geocoding failed for 1,811 records; these records were retained with missing coordinates at that step. Record-level deduplication does not establish incident-level uniqueness: different case numbers can refer to the same accident.

## Dataset fields

| Field | Description |
| --- | --- |
| `case_number` | Case number from the source judgment; not a guaranteed unique accident identifier |
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
| 3b. Incomplete-time supplement | `3.5 supplementary_incomplete_time.py` | Retain first-instance records excluded by the original hourly time rule; conservatively recover year/month/day information and preserve provenance |
| 5. Dataset assembly | `5.1 output_dataset.ipynb`, `5.2fillter_first.ipynb` | Assemble release fields, audit source-case-number ambiguity, synchronize record deduplication across stages 7/8/9, and retain first-instance judgments |
| 6. Validation sampling | `6.1 stratified_validation_sample.py` | Build an offline sampling frame and select 3,000 records using judgment year, court province and case type |

The extraction used Google Gemini 2.0 Flash (`gemini-2.0-flash-001`) through an OpenAI-compatible API with temperature set to 0 and JSON-constrained responses. Address descriptions were geocoded with the Baidu Maps API and converted to WGS84 coordinates.

## New and revised workflows

- **Incomplete-time supplement:** `3.5` takes the complement of the original hourly eligibility rule, then applies first-instance screening. It does not merge incidents or deduplicate by case number. `case_dt_hour` stays empty; derived precision is at most day-level. Ambiguous expressions and implausible dates are flagged rather than imputed. Its records must not all be described as a 2000–2020 accident cohort.
- **Temporal analysis (Fig. 3):** `4.3` reads stage 7, explicitly restricts timestamps to 2000-01-01 through 2020-12-31, records exclusions, and exports separate hour/month/year figures plus counts and QA summaries.
- **City analysis (Fig. 5):** `4.6` parses mixed date formats, excludes negative accident-to-judgment intervals, retains all cities with records, and records grouping/missingness counts. It applies no additional 2000–2020 filter. Its mortality flag proportion uses all retained records in each city as the denominator.
- **Assembly:** `5.1` retains the historical first-source-case-number join while writing an ambiguity audit; `5.2` invokes the same shared deduplication routine. These stages replace derived datasets, so retain your own backup before running them.
- **Validation sample:** `6.1` uses seed `20261107`, a minimum allocation of `min(2, N_h)` per nonempty stratum, proportional largest-remainder allocation of the remaining sample, and sampling without replacement within strata. Court province is a sampling variable, not the accident province. Creating the sample does not constitute completed manual/model validation.

### Embedded helpers and execution requirements

The recovered record-deduplication implementation is embedded directly in both `5.1` and `5.2`; the recovered Fig. 5 plotting implementation is embedded in `4.6`. No separately numbered helper files or local-module imports are required. The two copies of the deduplication definitions must be kept identical when editing them. The deduplication CLI entry point was omitted so that executing a notebook only defines the functions until the explicit workflow cell runs. DuckDB is required by this implementation.

The unavailable external `figure_panel_alignment` utility is replaced by an embedded check of panel bottom positions and heights (0.5-pixel tolerance) for the single-panel and horizontal two-panel exports. This is a geometry check, not a complete visual-overlap audit; the recovered plotting and regression logic is retained.

The `install` stage of `6.1` also expects existing external validation scripts and directories under `data/10.人工验证/`; those assets are not distributed here. Use `frame` and `sample` only after supplying their source data.

## Installation

Python 3.10 or newer is recommended. pandas 2.0 or newer is required for the mixed-format date parsing in `4.6`. Dependencies are not a locked reconstruction of the original execution environment.

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
├── code/                   # clone this repository with this directory name
├── data/                   # raw/intermediate/release inputs (not tracked)
├── figure/china_geodata/    # administrative boundaries (not tracked)
└── 检查重复/                 # generated audit outputs (not tracked)
```

Clone into a directory named `code` (`git clone https://github.com/LandscapeWL/Traffic-Accident-Code.git code`) and start Jupyter from that directory. This name is required by the project-root detection in `5.1` and `5.2`. Legacy notebooks also contain machine-specific Windows paths that must be edited before use. The geospatial stages require the referenced administrative boundary files.

From the parent project directory, the independent script entry points are:

```bash
python "code/3.5 supplementary_incomplete_time.py" --self-test
python "code/3.5 supplementary_incomplete_time.py"
python "code/6.1 stratified_validation_sample.py" frame
python "code/6.1 stratified_validation_sample.py" sample
```

The supplement writes to `data/7.1时间不完整补充数据/`; the validation sample writes to `data/10.人工验证/分层验证3000/`, with working caches in `.codex-task/stratified_validation_3000/`. The supplement requires all four stage-6 address CSV files and the merged source judgment CSV.

Notebook outputs are cleared for publication; the repository contains source code rather than a record of freshly executed results. Run notebooks interactively and inspect each input/output path before processing the full dataset. The geocoding and LLM steps call paid or rate-limited external services, so test them on a small sample first.

## Checks performed for this update

All 22 Python/notebook source files passed syntax checks, and the 16 notebooks passed schema validation. The incomplete-time parser's built-in boundary tests passed. A synthetic dataset verified exact-duplicate removal, missing-only record dominance, conflict retention, first-instance screening, synchronized stage-7/8/9 outputs and idempotence. The two embedded deduplication implementations were checked for equality. Full-corpus regeneration and external LLM/geocoding calls were not performed; the required raw inputs are not included here.

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
