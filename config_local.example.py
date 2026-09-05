"""config_local.py 模板 — 复制本文件为 config_local.py 并填入真实密钥。

config_local.py 被 .gitignore 排除，不会提交到 Git。
密钥读取优先级: 环境变量 > config_local.py > 空值（空值时对应功能不可用）。
"""

# Joplin Web Clipper API Token（Joplin 桌面端 → 工具 → 选项 → Web Clipper）
JOPLIN_TOKEN = ""

# 百度文本翻译 v2 API Token（bce-v3 Bearer）
BAIDU_MT_TOKEN = ""

# MiniMax API Key（默认 LLM 提供商，也用于 TTS_PROVIDER=minimax 鉴权）
MINIMAX_API_KEY = ""

# MiniMax TTS GroupID — 可选（新版端点实测可省略，留空即用账号默认组）
# 部分旧账号/备用端点 (api-bj) 需要；报“缺 GroupId”时再从账户中心获取填写。
MINIMAX_TTS_GROUP_ID = ""

# SiliconFlow API Key（备选 LLM 提供商）
SILICONFLOW_API_KEY = ""
