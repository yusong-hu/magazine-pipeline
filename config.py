"""统一配置 — 全流水线唯一配置来源。

路径、参数集中在此，均可用环境变量覆盖。
密钥不放本文件（本文件入 Git）：真实密钥放 config_local.py（不入库）
或环境变量。读取优先级: 环境变量 > config_local.py > 空值。
"""
import os
from pathlib import Path

try:
    import config_local  # 本地敏感配置（.gitignore 排除）
except ImportError:
    config_local = None


def _secret(name: str, default: str = "") -> str:
    """密钥读取: 环境变量 > config_local.py > 默认值。"""
    if os.environ.get(name):
        return os.environ[name]
    if config_local is not None:
        return getattr(config_local, name, default)
    return default


# ---------- 项目结构 ----------
PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = Path(os.environ.get("MAGPIPE_WORKSPACE_ROOT", PROJECT_ROOT / "workspace"))
DEFAULT_WORKSPACE = os.environ.get("MAGPIPE_WORKSPACE", "economist-2026-08-22")

# ---------- Joplin ----------
JOPLIN_BASE = os.environ.get("JOPLIN_BASE", "http://127.0.0.1:41184")
JOPLIN_TOKEN = _secret("JOPLIN_TOKEN")
# 笔记本优先用 ID（env 指定），否则按名称查找/创建
JOPLIN_NOTEBOOK_ID = os.environ.get("JOPLIN_NOTEBOOK_ID", "")
JOPLIN_NOTEBOOK_NAME = os.environ.get("JOPLIN_NOTEBOOK_NAME", "22_经济学人")

# ---------- TTS 引擎 ----------
TTS_ENGINE = PROJECT_ROOT / "text-to-speech" / "scripts" / "tts_generate.py"
TTS_PYTHON = os.environ.get("MAGPIPE_TTS_PYTHON", "/tmp/edge-tts-env/bin/python")
VOICE_EN = os.environ.get("MAGPIPE_VOICE_EN", "en-GB-RyanNeural")
VOICE_ZH = os.environ.get("MAGPIPE_VOICE_ZH", "zh-CN-YunyangNeural")
TTS_COOLDOWN = float(os.environ.get("MAGPIPE_TTS_COOLDOWN", "3"))
TTS_MAX_CHARS = int(os.environ.get("MAGPIPE_TTS_MAX_CHARS", "250"))

# ---------- 百度翻译 API ----------
BAIDU_MT_URL = "https://aip.baidubce.com/rpc/2.0/mt/texttrans/v2"
BAIDU_MT_TOKEN = _secret("BAIDU_MT_TOKEN")
BAIDU_MT_MAX_CHARS = 4000       # 单次请求 q 的保守上限（官方上限约 6000 字节）
BAIDU_MT_CONCURRENCY = 2        # 并发上限，避免触发限流
BAIDU_MT_RETRY_WAIT = 10        # 限流后等待秒数再重试
BAIDU_MT_MAX_RETRIES = 5

# ---------- LLM 提供商（翻译 + 解读共用，均走 Anthropic 兼容 Messages 协议） ----------
# 提供商切换: LLM_PROVIDER=minimax | siliconflow（模型/密钥按提供商独立配置）
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "minimax")

# MiniMax（默认提供商）— 国内端点；模型可选 MiniMax-M3 / M2.7 / M2.5 / M2.1 / M2 等
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com")
MINIMAX_API_KEY = _secret("MINIMAX_API_KEY")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")

# SiliconFlow（备选提供商）
SILICONFLOW_BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn")
SILICONFLOW_API_KEY = _secret("SILICONFLOW_API_KEY")
SILICONFLOW_MODEL = os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V4-Flash")

# LLM 通用参数（跨提供商共享）
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "16384"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))          # 秒
LLM_MAX_INPUT_CHARS = int(os.environ.get("LLM_MAX_INPUT_CHARS", "40000"))
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "2"))    # 并发上限
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))

# ---------- 翻译引擎 ----------
# llm   = 大模型翻译（走 LLM_PROVIDER，默认 MiniMax，质量更好）
# baidu = 百度机器翻译（便宜、快，长文分块）
TRANSLATE_ENGINE = os.environ.get("TRANSLATE_ENGINE", "llm")
# LLM 翻译单块最大字符数（分块保留段落边界）
LLM_TRANSLATE_MAX_CHARS = int(os.environ.get("LLM_TRANSLATE_MAX_CHARS", "6000"))

# ---------- 中文文档数据契约（结构标记） ----------
ZH_SECTION_TRANSLATION = "## 中文全文翻译"
ZH_SECTION_ANALYSIS = "## 中文解析"

# ---------- 笔记标题后缀 ----------
NOTE_TITLE_SUFFIX = "— 英中对照 + 文章讲解"
