import os

src = r"E:\202512LLM交通\data\6.匹配地点/address_transport_result_3_4.csv"
dst = r"E:\202512LLM交通\data\6.匹配地点/address_transport_result_3_4-utf.csv"

with open(src, "r", encoding="gb18030", newline="") as f_in, \
     open(dst, "w", encoding="utf-8-sig", newline="") as f_out:
    for line in f_in:
        f_out.write(line)

print("done:", dst)
