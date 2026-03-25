import os
import json
from openai import OpenAI
import pandas as pd

# ---------- 路径 ----------
in_path = "../data/3.数据合并/裁判文书网2000-2021_last1w.csv"
out_path = "../data/4.数据处理/transport_result_1w.csv"

# ---------- 读取 ----------
df = pd.read_csv(in_path)

# ---------- OpenAI Client ----------
client = OpenAI(
    base_url="https://api.zetatechs.com/v1",
    api_key="sk-IciKuJueph4IwRYCoJeEFF4UyiPGMCECDZh1E4ciL1nFvIn6"
)
MODEL = "gemini-2.0-flash-001"

SYSTEM_PROMPT = """你是专业的法律文件分析助理。请从提供的文本中提取交通事故发生的时间、省份、城市、行政区、具体地点、交通工具、是否死亡。
请从提供的文本中提取信息，并严格返回以下JSON格式。如果有字段无法准确提取，请返回空字段。请勿添加任何其他格式或标记：
{"case_time": "YYYY年MM月DD日HH时(案件发生时间,不是判决落款时间、不是书记员时间、不是立案时间)",
  "province": "案件发生省份",
  "city": "案件发生城市",
  "district": "案件发生行政区",
  "specific_place": "案件发生具体地点（尽量用原文说法若无法精确到街道请返回空字段）",
  "vehicle": "0=汽车事故；1=汽车与摩托/电动车；2=汽车与行人；3=摩托/电动车与行人",
  "death": "0=无人死亡；1=有人死亡"}
"""

def call_llm(row):
    court_name = row.get("法院")
    court_area = row.get("所属地区")
    judgment = row.get("全文")

    text = f"法院：{court_name}。所属地区：{court_area}。全文：{judgment}。"
    text = (text or "")[:1000] # 截断文字前1000

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": text}],
        temperature=0,
        response_format={"type": "json_object"})

    raw = resp.choices[0].message.content
    obj = json.loads(raw)

    # 兼容：有些模型可能返回 [ {...} ]
    if isinstance(obj, list):
        obj = obj[0] if obj else {}

    return obj

# ===================== 断点续跑（最少改动） =====================
start_i = 0
if os.path.exists(out_path):
    try:
        done = pd.read_csv(out_path, usecols=["row_id"])
        if not done.empty:
            start_i = int(done["row_id"].max()) + 1
    except Exception:
        # 兜底：如果输出CSV末尾损坏导致pandas读不了，就按行数估算
        with open(out_path, "r", encoding="utf-8-sig") as f:
            start_i = max(sum(1 for _ in f) - 1, 0)

    print(f"resume from row_id={start_i} (skip 0~{start_i-1})")
# ===================================================================

file_exists = os.path.exists(out_path)

# 原来是：for i, row in df.iterrows():
for i in range(start_i, len(df)):
    row = df.iloc[i]

    info = call_llm(row)

    # 可选：保留原始定位字段，便于回溯
    record = {
        "row_id": i,
        "案号": row.get("案号"),
        "裁判日期": row.get("裁判日期"),
        "当事人": row.get("当事人"),
        **info
    }

    pd.DataFrame([record]).to_csv(
        out_path,
        mode="a",
        index=False,
        header=not file_exists,
        encoding="utf-8-sig"
    )
    file_exists = True  # 写过一次后，后续都不再写header

    print(f"saved: {i+1}/{len(df)}")