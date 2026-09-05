# 杂志流水线 (magazine-pipeline)

英文杂志（纽约客 / 经济学人等 EPUB）→ 提取 → LLM/百度翻译 → LLM 中文解读 → Edge TTS 朗读 → 导入 Joplin。

## 设计思路

- **分层解耦**：`config`（唯一配置）→ `core`（公共工具）→ 各阶段模块（extract / translate / tts / importer），依赖只向下、不横向。
- **数据契约**：阶段间文件传递的路径与命名规则全部收敛在 `core/contract.py::Workspace`，业务代码禁止手拼路径。
- **配置外置**：所有路径、Token、音色、并发参数集中在 `config.py`，支持环境变量覆盖，换一期杂志/账号零代码改动。
- **幂等可续**：每个阶段对已完成的产物自动跳过（翻译跳过已有 zh、TTS 跳过已有 mp3、导入双重去重），可安全重跑。
- **零第三方依赖**：HTTP 全部基于 stdlib `urllib`（`core/http.py`），任何 Python ≥ 3.10 环境可直接运行。

## 目录结构

```
config.py          统一配置（env 可覆盖）
core/
  contract.py      工作区路径契约（articles/ articles-zh/ tts_inputs/ audio/ .state/）
  markdown_utils.py frontmatter 解析、中英拆分、md→纯文本
  text_utils.py    段落分块（翻译引擎共用）
  http.py          stdlib HTTP 客户端（Joplin/百度/LLM 统一经此）
  llm_client.py    统一 LLM 客户端（多提供商切换，Anthropic 兼容协议）
  joplin_client.py Joplin Web API 唯一封装
extract/extract_epub.py   通用 EPUB 提取（nav.xhtml 目录 + 语义化 class 自适应）
translate/
  __init__.py       引擎分发（TRANSLATE_ENGINE: llm | baidu）
  llm_translate.py  LLM 翻译（默认 MiniMax，分块保留段落、并发可调）
  baidu_translate.py 百度翻译（分块、并发≤2、限流 10s 退避重试）
analyze/llm_analysis.py   LLM 中文解读（8 小节精读格式，走统一 LLM 客户端）
tts/
  prepare_inputs.py   生成 3 个朗读输入（en / zh_tr / zh_an）
  generate_audio.py   调用 text-to-speech 引擎（断点续传）
importer/import_joplin.py  统一导入（按名称解析笔记本、状态+标题双去重、--force 原地更新、--watch）
pipeline.py        统一 CLI 入口
workspace/<期号>/  数据工作区（代码与资源分离）
legacy/            旧版脚本归档
```

## LLM 提供商与模型选择

翻译（LLM 引擎）与解读共用一套 LLM 配置，在 `config.py` 或环境变量中选择：

```bash
# 提供商切换（默认 minimax）
LLM_PROVIDER=minimax        # MiniMax（默认）
LLM_PROVIDER=siliconflow    # SiliconFlow 备选

# MiniMax（默认）— 模型可选 MiniMax-M3 / M2.7 / M2.5 / M2.1 / M2 等
MINIMAX_MODEL=MiniMax-M2.5

# SiliconFlow 备选
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash

# 翻译引擎切换（默认 llm；llm 走上述 LLM_PROVIDER）
TRANSLATE_ENGINE=llm        # 大模型翻译（质量更好）
TRANSLATE_ENGINE=baidu      # 百度机翻（便宜、快）

# 通用参数
LLM_CONCURRENCY=2           # 并发上限
LLM_MAX_TOKENS=16384
LLM_TIMEOUT=600
```

## 技术选型

| 环节 | 方案 | 理由 |
|------|------|------|
| 提取 | stdlib `html.parser` + `zipfile` | EPUB 即 zip+xhtml，语义化 class 足够，无需重依赖 |
| 翻译 | LLM（默认 MiniMax）/ 百度文本翻译 v2 | LLM 译文达出版水准、保留 Markdown 结构；百度作低成本备选 |
| 解读 | 统一 LLM 客户端（默认 MiniMax-M2.5） | 结构化 8 小节精读；thinking 块自动过滤、限流退避重试 |
| TTS | edge-tts（本地 skill 引擎） | 免费、音质好、自带断点续传；ffmpeg 合并 |
| 导入 | Joplin Web Clipper API | 本地 HTTP，`:/resource_id` 内嵌音频 |

## 用法

```bash
# 全流程（单篇：翻译→解读→TTS→导入）
python3 pipeline.py extract --epub TheEconomist.2026.08.22.epub   # 提取整期
python3 pipeline.py run --num 1                                    # 一键流程

# 分阶段
python3 pipeline.py translate --num 1 | --all
python3 pipeline.py analyze  --num 1 | --all [--force]   # 重新生成解读
python3 pipeline.py tts      --num 1 | --all
python3 pipeline.py import   --num 1 | --all [--force] [--watch]
# import --force: 已有笔记原地更新（如补充解析后重建），不产生重复

# 换一期杂志
python3 pipeline.py extract --epub OtherMagazine.epub --workspace other-2026-09-01
python3 pipeline.py run --num 1 --workspace other-2026-09-01
```

## 环境依赖

- Python 3.10+（主流程）；TTS 引擎运行于 `/tmp/edge-tts-env`（可经 `MAGPIPE_TTS_PYTHON` 覆盖）
- `edge-tts`、`ffmpeg`
- Joplin 桌面端开启 Web Clipper（`工具 → 选项 → Web Clipper`）
