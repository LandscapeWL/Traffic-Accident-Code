"""Convert existing Baidu BD-09LL coordinates to WGS84.

Run this script once after all Baidu geocoding and failed-record retries have
finished, and before running ``3.3 time_calculation.ipynb``.

Only the ``lng`` and ``lat`` values are changed. Column names, row order, and
all other field values are preserved. Each original CSV is retained as a
``.bd09ll.bak`` backup before the converted file replaces it.
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path


X_PI = math.pi * 3000.0 / 180.0
A = 6378245.0
EE = 0.00669342162296594323

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data" / "6.匹配地点"
INPUT_FILES = [
    DATA_DIR / f"address_transport_result_{part}_4.csv"
    for part in range(1, 5)
]


def bd09_to_gcj02(bd_lng: float, bd_lat: float) -> tuple[float, float]:
    """Convert BD-09 latitude/longitude to GCJ-02."""
    x = bd_lng - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def transform_lat(lng: float, lat: float) -> float:
    result = (
        -100.0
        + 2.0 * lng
        + 3.0 * lat
        + 0.2 * lat * lat
        + 0.1 * lng * lat
        + 0.2 * math.sqrt(abs(lng))
    )
    result += (
        20.0 * math.sin(6.0 * lng * math.pi)
        + 20.0 * math.sin(2.0 * lng * math.pi)
    ) * 2.0 / 3.0
    result += (
        20.0 * math.sin(lat * math.pi)
        + 40.0 * math.sin(lat / 3.0 * math.pi)
    ) * 2.0 / 3.0
    result += (
        160.0 * math.sin(lat / 12.0 * math.pi)
        + 320.0 * math.sin(lat * math.pi / 30.0)
    ) * 2.0 / 3.0
    return result


def transform_lng(lng: float, lat: float) -> float:
    result = (
        300.0
        + lng
        + 2.0 * lat
        + 0.1 * lng * lng
        + 0.1 * lng * lat
        + 0.1 * math.sqrt(abs(lng))
    )
    result += (
        20.0 * math.sin(6.0 * lng * math.pi)
        + 20.0 * math.sin(2.0 * lng * math.pi)
    ) * 2.0 / 3.0
    result += (
        20.0 * math.sin(lng * math.pi)
        + 40.0 * math.sin(lng / 3.0 * math.pi)
    ) * 2.0 / 3.0
    result += (
        150.0 * math.sin(lng / 12.0 * math.pi)
        + 300.0 * math.sin(lng / 30.0 * math.pi)
    ) * 2.0 / 3.0
    return result


def wgs84_to_gcj02(wgs_lng: float, wgs_lat: float) -> tuple[float, float]:
    """Forward transform used to iteratively invert GCJ-02."""
    if out_of_china(wgs_lng, wgs_lat):
        return wgs_lng, wgs_lat

    d_lat = transform_lat(wgs_lng - 105.0, wgs_lat - 35.0)
    d_lng = transform_lng(wgs_lng - 105.0, wgs_lat - 35.0)
    rad_lat = wgs_lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1.0 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)

    d_lat = (
        d_lat
        * 180.0
        / ((A * (1.0 - EE)) / (magic * sqrt_magic) * math.pi)
    )
    d_lng = (
        d_lng
        * 180.0
        / (A / sqrt_magic * math.cos(rad_lat) * math.pi)
    )
    return wgs_lng + d_lng, wgs_lat + d_lat


def gcj02_to_wgs84(
    gcj_lng: float,
    gcj_lat: float,
    iterations: int = 6,
) -> tuple[float, float]:
    """Iteratively invert GCJ-02 to obtain WGS84 coordinates."""
    if out_of_china(gcj_lng, gcj_lat):
        return gcj_lng, gcj_lat

    wgs_lng = gcj_lng
    wgs_lat = gcj_lat
    for _ in range(iterations):
        estimated_lng, estimated_lat = wgs84_to_gcj02(wgs_lng, wgs_lat)
        wgs_lng -= estimated_lng - gcj_lng
        wgs_lat -= estimated_lat - gcj_lat
    return wgs_lng, wgs_lat


def bd09_to_wgs84(bd_lng: float, bd_lat: float) -> tuple[float, float]:
    """Convert BD-09LL to WGS84 through GCJ-02."""
    gcj_lng, gcj_lat = bd09_to_gcj02(bd_lng, bd_lat)
    return gcj02_to_wgs84(gcj_lng, gcj_lat)


def convert_file(input_path: Path) -> tuple[int, int]:
    temp_path = input_path.with_name(input_path.name + ".wgs84.tmp")
    backup_path = input_path.with_name(input_path.name + ".bd09ll.bak")

    if backup_path.exists():
        raise RuntimeError(
            "A BD-09LL backup already exists; this file may already have been "
            f"converted. Refusing to run twice: {backup_path}"
        )

    converted_count = 0
    skipped_count = 0

    try:
        with input_path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as input_file, temp_path.open(
            "w", encoding="utf-8-sig", newline=""
        ) as output_file:
            reader = csv.DictReader(input_file)
            fieldnames = reader.fieldnames or []
            if "lng" not in fieldnames or "lat" not in fieldnames:
                raise ValueError(f"Missing lng or lat column: {input_path}")

            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                try:
                    bd_lng = float(row["lng"])
                    bd_lat = float(row["lat"])
                    if not (
                        math.isfinite(bd_lng)
                        and math.isfinite(bd_lat)
                        and -180.0 <= bd_lng <= 180.0
                        and -90.0 <= bd_lat <= 90.0
                    ):
                        raise ValueError("Invalid coordinate")

                    wgs_lng, wgs_lat = bd09_to_wgs84(bd_lng, bd_lat)
                    row["lng"] = f"{wgs_lng:.12f}"
                    row["lat"] = f"{wgs_lat:.12f}"
                    converted_count += 1
                except (TypeError, ValueError):
                    # Preserve blank or invalid coordinate values unchanged.
                    skipped_count += 1

                writer.writerow(row)

        # Keep the source data recoverable, then atomically install the result.
        os.replace(input_path, backup_path)
        os.replace(temp_path, input_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    return converted_count, skipped_count


def main() -> None:
    missing_files = [path for path in INPUT_FILES if not path.exists()]
    if missing_files:
        missing_text = "\n".join(str(path) for path in missing_files)
        raise FileNotFoundError(f"Missing input files:\n{missing_text}")

    print(f"Coordinate conversion directory: {DATA_DIR}")
    print("Input CRS: BD-09LL; output CRS: WGS84 (EPSG:4326)")

    for input_path in INPUT_FILES:
        converted, skipped = convert_file(input_path)
        print(
            f"Completed {input_path.name}: converted={converted}, "
            f"skipped={skipped}"
        )
        print(f"Backup: {input_path.name}.bd09ll.bak")

    print("All four coordinate files have been converted successfully.")
    print("Next step: run 3.3 time_calculation.ipynb for parts 1-4.")


if __name__ == "__main__":
    main()
