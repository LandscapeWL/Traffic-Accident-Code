"""生成未通过原时间规则的一审补充记录；不修改原流水线及任何原始文件。

运行：python "code/3.5 supplementary_incomplete_time.py"
验证解析边界：python "code/3.5 supplementary_incomplete_time.py" --self-test

输入：data/6.匹配地点/address_transport_result_{1..4}_4.csv；
data/3.数据合并/裁判文书网2000-2021.csv（连接法院和全文）。
唯一正式输出：data/7.1时间不完整补充数据/
    ChinaTransportDatas_incomplete_time_first_instance.csv

纳入规则：复现 3.3 的原时间资格规则，取其补集，再应用 5.2 的一审规则。
不按事故年份、坐标是否缺失额外排除，不做事故级或案号级去重。
因此，输出不能整体称为 2000—2020 年事故队列，也不是独立事故数。

前 13 列与最终主数据的字段名、顺序一致；case_dt_hour 全部为空，表示未提供
经本脚本确认的小时级时间，不代表原文必然没有小时。法院/全文沿用 5.1 的
首次案号匹配规则；未匹配或源字段缺失时留空。主数据文件不修改。
vehicle/death 统一为整数类别和空值，并在 vehicle_raw/death_raw 留存原值。
保留输入的全部字段（案号/裁判日期/当事人分别改名为
case_number/judgment_date/privy），并新增：
  source_file, source_row: 源文件名及从 1 开始的数据记录序号（不是文本行号）；
  exclusion_reason: empty_time / unmatched_hour_format / invalid_datetime；
  accident_year/month/day/date: 通过保守规则验证的日级及更粗时间信息；
  time_precision: 此脚本确认的精度 unknown/year/month/day，最高只到日；
  time_parse_status: missing/unparsed/ambiguous/invalid_year/invalid_month/
    invalid_date/parsed_year/parsed_month/parsed_date/suspect_year/
    accident_after_judgment。

原始 case_time 不改动。新解析只处理单一、明确的中文年月日表达；区间、
多日期、多个时间及不确定表达留待核查。缺月/日不补 1，缺小时不补 0。
time_precision=day 不代表原文没有小时，只表示本补充脚本不解析小时。
日期合法但时钟无效时，仍可以恢复日期。事故年份超出 1900—2021 的宽松
核查范围，或事故时间在其已知精度上晚于裁判日期时，派生分量清空并标记
待核查；原始文本与记录仍保留，不猜测更正年份。
终端打印计数和验证结果，不生成另外两份统计 CSV。
"""

from __future__ import annotations

import argparse
import calendar
from collections import Counter
from datetime import date
from pathlib import Path
import re
import sqlite3
import unicodedata

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CORE_COLUMNS = ['case_number', 'privy', 'province', 'city', 'district',
                'specific_place', 'vehicle', 'death', 'lng', 'lat',
                'case_dt_hour', 'court_name', 'case_text']
# 宽松的年份合理性核查范围，并非研究队列的 2000—2020 纳入条件。
# 源裁判资料截止 2021 年；1900 年以前的事故时间需人工确认。
MIN_PLAUSIBLE_YEAR, MAX_SOURCE_YEAR = 1900, 2021
LEGACY_PATTERN = (
    r"(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
    r"(?P<hour>\d{1,2})时(?:(?P<minute>\d{1,2})分)?"
)
CIVIL_PATTERN = r"民(?:一|二|三)?初(?:字)?"
CRIMINAL_PATTERN = r"刑(?:一|二)?初(?:字)?"
DATE_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})年"
    r"(?:(?P<month>[0-9]{1,2})月(?:(?P<day>[0-9]{1,2})日)?)?"
)
DERIVED_COLUMNS = [
    "accident_year", "accident_month", "accident_day", "accident_date",
    "time_precision", "time_parse_status",
]


def legacy_status(times: pd.Series) -> pd.Series:
    """完全复现旧资格判断；不对旧规则额外做 NFKC 或范围修复。"""
    s = times.astype("string").str.strip()
    empty = s.isna() | s.eq("").fillna(False)
    parts = s.str.extract(LEGACY_PATTERN)
    matched = parts[["year", "month", "day", "hour"]].notna().all(axis=1)
    numeric = parts.apply(pd.to_numeric, errors="coerce").astype("float64")
    numeric["minute"] = numeric["minute"].fillna(0)
    dt = pd.to_datetime(numeric, errors="coerce")
    status = pd.Series("unmatched_hour_format", index=times.index, dtype="string")
    status.loc[empty] = "empty_time"
    status.loc[matched & dt.isna()] = "invalid_datetime"
    status.loc[matched & dt.notna()] = "legacy_eligible"
    return status


def first_instance(case_numbers: pd.Series) -> pd.Series:
    normalized = (
        case_numbers.astype("string").fillna("").str.normalize("NFKC")
        .str.replace(r"\s+", "", regex=True)
    )
    return normalized.str.contains(
        CIVIL_PATTERN + "|" + CRIMINAL_PATTERN, regex=True, na=False
    )


def parse_calendar_date(raw):
    """返回经验证的连续时间分量，不猜测缺失信息。"""
    result = [None, None, None, None, "unknown", "unparsed"]
    if pd.isna(raw) or not str(raw).strip():
        result[-1] = "missing"
        return result
    s = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(raw)))
    # 宁可少恢复，也不将区间起点或多个事故中的第一天当成唯一事故时间。
    if (
        re.search(r"至|到|期间|之间|或|不详|不明|左右|前后|约|某|[~～—–-]", s)
        or s.count("年") > 1 or s.count("月") > 1 or s.count("日") > 1
        or s.count("时") > 1
    ):
        result[-1] = "ambiguous"
        return result
    match = DATE_PATTERN.match(s)
    if match is None:
        return result
    y = int(match["year"])
    if not 1 <= y <= 9999:
        result[-1] = "invalid_year"
        return result
    result[0], result[4], result[5] = y, "year", "parsed_year"
    if match["month"] is None:
        return result
    m = int(match["month"])
    if not 1 <= m <= 12:
        result[-1] = "invalid_month"
        return result
    result[1], result[4], result[5] = m, "month", "parsed_month"
    if match["day"] is None:
        return result
    d = int(match["day"])
    if not 1 <= d <= calendar.monthrange(y, m)[1]:
        result[-1] = "invalid_date"
        return result
    result[2:6] = [d, date(y, m, d).isoformat(), "day", "parsed_date"]
    return result


def parse_date(raw, judgment_date=None):
    result = parse_calendar_date(raw)
    y, m, d = result[:3]
    if y is None:
        return result
    if not MIN_PLAUSIBLE_YEAR <= y <= MAX_SOURCE_YEAR:
        return [None, None, None, None, 'unknown', 'suspect_year']
    # 按已知精度判断先后；未知月日不补值。
    if judgment_date is not None and not pd.isna(judgment_date):
        j = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})', str(judgment_date))
        if j:
            try:
                jd = date(*map(int, j.groups()))
            except ValueError:
                jd = None
            if jd is not None:
                after = y > jd.year
                if m is not None:
                    after = (y, m) > (jd.year, jd.month)
                if d is not None:
                    after = date(y, m, d) > jd
                if after:
                    return [None, None, None, None, 'unknown', 'accident_after_judgment']
    return result


def normalize_category(values, allowed):
    numeric = pd.to_numeric(values, errors='coerce')
    return numeric.where(numeric.isin(allowed)).astype('Int64')


def attach_release_fields(staging, destination):
    """与 5.1 一样按案号连接、取源合并文件第一次出现的法院/全文。

    SQLite 只缓存目标案号，避免把数 GB 全文同时加载到内存。
    两侧重复案号不会导致行数膨胀；不对补充记录进行去重。
    """
    target = set(pd.read_csv(staging, usecols=['case_number'], dtype='string')['case_number'])
    source = ROOT / 'data/3.数据合并/裁判文书网2000-2021.csv'
    cache = ROOT / '.codex-task/r2_3_release_lookup.sqlite'
    cache.parent.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    with sqlite3.connect(cache) as db:
        db.execute('DROP TABLE IF EXISTS records')
        db.execute('CREATE TABLE records (case_number TEXT PRIMARY KEY, court_name TEXT, case_text TEXT)')
        seen = set()
        for i, chunk in enumerate(pd.read_csv(source, usecols=['案号', '法院', '全文'], dtype='string', chunksize=20000), 1):
            selected = chunk.loc[chunk['案号'].isin(target - seen)].drop_duplicates('案号', keep='first')
            rows = list(selected[['案号', '法院', '全文']].fillna('').itertuples(index=False, name=None))
            db.executemany('INSERT INTO records VALUES (?, ?, ?)', rows)
            seen.update(selected['案号'])
            db.commit()
            if i % 20 == 0:
                print(f'Lookup scanned {i * 20000:,} rows; matched {len(seen):,} case numbers', flush=True)
        stats['unmatched_case_numbers'] = len(target - seen)
        with destination.open('w', encoding='utf-8-sig', newline='') as stream:
            for i, chunk in enumerate(pd.read_csv(staging, dtype='string', chunksize=10000)):
                values = [db.execute('SELECT court_name, case_text FROM records WHERE case_number=?', (key,)).fetchone()
                          for key in chunk['case_number']]
                stats['unmatched_records'] += sum(v is None for v in values)
                chunk['court_name'] = [v[0] if v else '' for v in values]
                chunk['case_text'] = [v[1] if v else '' for v in values]
                stats['missing_court_name'] += int(chunk['court_name'].eq('').sum())
                stats['missing_case_text'] += int(chunk['case_text'].eq('').sum())
                chunk['case_dt_hour'] = pd.NA
                for col, allowed in [('vehicle', [0, 1, 2, 3]), ('death', [0, 1])]:
                    chunk[col + '_raw'] = chunk[col]
                    normalized = normalize_category(chunk[col], allowed)
                    stats[col + '_invalid_to_missing'] += int((chunk[col].notna() & normalized.isna()).sum())
                    chunk[col] = normalized
                order = CORE_COLUMNS + [c for c in chunk.columns if c not in CORE_COLUMNS]
                chunk[order].to_csv(stream, index=False, header=i == 0)
    # 缓存位于固定工作目录，成功导出后只删除此单一临时文件。
    db.close()
    cache.unlink()
    print('Release enrichment:', dict(stats), flush=True)
    return stats


def self_test():
    cases = {
        "2015年": [2015, None, None, None, "year", "parsed_year"],
        "2015年6月": [2015, 6, None, None, "month", "parsed_month"],
        "2002年11月3日上午8时": [2002, 11, 3, "2002-11-03", "day", "parsed_date"],
        "2020年2月29日晚": [2020, 2, 29, "2020-02-29", "day", "parsed_date"],
        "2019年2月29日": [2019, 2, None, None, "month", "invalid_date"],
        "2020年13月1日": [2020, None, None, None, "year", "invalid_month"],
        "2020年1月1日至2日": [None, None, None, None, "unknown", "ambiguous"],
        "": [None, None, None, None, "unknown", "missing"],
    }
    for raw, expected in cases.items():
        assert parse_date(raw) == expected, (raw, parse_date(raw), expected)
    values = pd.Series(["2020年1月1日8时", "2020年1月1日", None,
                        "2019年2月29日8时", "2002年11月3日上午8时"], dtype="string")
    assert legacy_status(values).tolist() == [
        "legacy_eligible", "unmatched_hour_format", "empty_time",
        "invalid_datetime", "unmatched_hour_format",
    ]
    assert first_instance(pd.Series(["（2020）京民初1号", "刑初字1号", "民终1号"])).tolist() == [True, True, False]
    for raw in ['3011年8月23日', '3013年4月6日', '2915年12月17日', '1016年6月17日']:
        assert parse_date(raw)[-1] == 'suspect_year'
        assert parse_date(raw)[:4] == [None] * 4
    assert parse_date('2019年6月1日', '2019/5/31')[-1] == 'accident_after_judgment'
    assert parse_date('2019年', '2019/5/31')[0] == 2019
    assert parse_date('1999年12月31日', '2000/1/1')[3] == '1999-12-31'
    assert normalize_category(pd.Series(['0', '1.0', '未知', '4', None]), [0, 1, 2, 3]).fillna(-1).tolist() == [0, 1, -1, -1, -1]
    print("Boundary checks passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="允许替换已生成的补充文件")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    inputs = [ROOT / "data" / "6.匹配地点" / f"address_transport_result_{i}_4.csv" for i in range(1, 5)]
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(path)
    output = ROOT / "data" / "7.1时间不完整补充数据" / "ChinaTransportDatas_incomplete_time_first_instance.csv"
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists; use --overwrite to replace: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".csv.tmp")
    counts, reasons, precisions, parse_statuses = Counter(), Counter(), Counter(), Counter()
    expected_columns = None
    with temp.open("w", encoding="utf-8-sig", newline="") as stream:
        wrote_header = False
        for path in inputs:
            offset = 0
            for chunk in pd.read_csv(path, dtype="string", chunksize=100_000):
                if expected_columns is None:
                    expected_columns = chunk.columns.tolist()
                if chunk.columns.tolist() != expected_columns:
                    raise ValueError(f"Source schema mismatch: {path}")
                status = legacy_status(chunk["case_time"])
                first = first_instance(chunk["案号"])
                eligible = status.eq("legacy_eligible")
                keep = first & ~eligible
                counts.update(source=len(chunk), first=int(first.sum()),
                              core=int((first & eligible).sum()), supplemental=int(keep.sum()))
                selected = chunk.loc[keep].copy()
                selected["source_file"] = path.name
                # read_csv 的块索引在整个文件内连续；用局部位置显式计算来源序号。
                positions = pd.Series(range(offset + 1, offset + len(chunk) + 1), index=chunk.index)
                selected["source_row"] = positions.loc[keep]
                offset += len(chunk)
                selected["exclusion_reason"] = status.loc[keep]
                parsed = pd.DataFrame(
                    [parse_date(v, j) for v, j in zip(selected["case_time"], selected['裁判日期'])],
                    index=selected.index, columns=DERIVED_COLUMNS,
                )
                for column in DERIVED_COLUMNS[:3]:
                    parsed[column] = parsed[column].astype("Int64")
                selected = pd.concat([selected, parsed], axis=1).rename(columns={
                    "案号": "case_number", "裁判日期": "judgment_date", "当事人": "privy",
                })
                reasons.update(selected["exclusion_reason"])
                precisions.update(selected["time_precision"])
                parse_statuses.update(selected["time_parse_status"])
                selected.to_csv(stream, index=False, header=not wrote_header)
                wrote_header = True
            print(f"Processed {path.name}: {offset:,} records", flush=True)
    assert counts["first"] == counts["core"] + counts["supplemental"]
    # 回读实际写出的文件，核对来源键唯一性、纳入规则及日期派生结果。
    check = pd.read_csv(temp, dtype="string")
    assert len(check) == counts["supplemental"]
    assert not check.duplicated(["source_file", "source_row"]).any()
    assert first_instance(check["case_number"]).all()
    assert legacy_status(check["case_time"]).eq(check["exclusion_reason"]).all()
    assert not check["exclusion_reason"].eq("legacy_eligible").any()
    for raw, judgment, values in zip(check["case_time"], check['judgment_date'], check[DERIVED_COLUMNS].itertuples(index=False, name=None)):
        expected = [None if x is None else str(x) for x in parse_date(raw, judgment)]
        actual = [None if pd.isna(x) else str(x) for x in values]
        assert actual == expected, "Derived fields changed during CSV serialization"
    release_temp = output.with_suffix('.release.tmp')
    enrichment = attach_release_fields(temp, release_temp)
    # 全量回读最终文件：验证列顺序、原始记录对应关系、类别域和空小时。
    written = 0
    for part in pd.read_csv(release_temp, dtype='string', chunksize=10000):
        assert part.columns[:13].tolist() == CORE_COLUMNS
        assert part['case_dt_hour'].isna().all()
        for c, domain in [('vehicle', ['0', '1', '2', '3']), ('death', ['0', '1'])]:
            assert part[c].dropna().isin(domain).all()
        reference = check.iloc[written:written + len(part)].reset_index(drop=True)
        actual = part.reset_index(drop=True)
        for col in check.columns:
            target_col = col + '_raw' if col in ['vehicle', 'death'] else col
            assert reference[col].fillna('').equals(actual[target_col].fillna('')), col
        written += len(part)
    assert written == counts['supplemental']
    # 比较与序列化检查成功后才原子替换已有补充文件。
    release_temp.replace(output)
    temp.unlink()
    print("Counts:", dict(counts))
    print("Exclusion reasons:", dict(reasons))
    print("Recovered precision (maximum day):", dict(precisions))
    print("Parse statuses:", dict(parse_statuses))
    print("Validation passed. Output:", output)


if __name__ == "__main__":
    main()
