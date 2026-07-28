import os
from openai import OpenAI

# 1) 连接到 Ollama/vllm 的 OpenAI 兼容接口
client = OpenAI(base_url="https://api.zetatechs.com/v1", api_key=os.environ["LLM_API_KEY"])  # 这里随便填，LM Studio 一般不校验

# 2) 填模型名
MODEL = "gemini-2.5-flash-lite-nothinking"

# 3) 直接在代码里写好对话内容
messages = [ {"role": "system", "content": "你是一个有帮助的助手。"},
             {"role": "user", "content": "你是什么型号的模型？有多少B的参数？4B还是8B"},]

# 4) 只调用一次
resp = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    # temperature=0.9,
)

print("Assistant:", resp.choices[0].message.content)
