# 杂志流水线 (magazine-pipeline)

英文杂志（纽约客 / 经济学人等 EPUB）→ 提取 → LLM/百度翻译 → LLM 中文解读 → TTS 朗读（本地 edge-tts 或云端 MiniMax）→ 导入 Joplin。

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
  generate_audio.py   语音引擎分发（TTS_PROVIDER: edge | minimax，断点续传）
  minimax_tts.py      MiniMax t2a_v2 合成（文本分块→hex 解码→协议拼接 mp3）
run_issue.py        整期一键脚本（逐篇串行 翻译→解读→TTS→导入，单篇失败不中断）
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
# ⚠️ 试错机制：TRANSLATE_ENGINE=llm 时，LLM 翻译遇敏感词/异常会自动回退百度机翻，
#   整期不因单篇内容问题中断；中文解读遇敏感词报错则输出"含敏感信息"跳过该篇继续。

# 通用参数
LLM_CONCURRENCY=2           # 并发上限
LLM_MAX_TOKENS=16384
LLM_TIMEOUT=600
```

## 语音引擎（TTS）选择

用 `TTS_PROVIDER` 切换朗读引擎（默认 `edge`，本地免费）：

```bash
TTS_PROVIDER=edge           # 本地 edge-tts（零成本，需装 /tmp/edge-tts-env）
TTS_PROVIDER=minimax        # MiniMax t2a_v2 云端合成（CodingPlan 含语音额度）
```

仅 `TTS_PROVIDER=minimax` 生效的参数（均在 config.py，可用环境变量覆盖）：

| 参数 | 默认 | 说明 |
|------|------|------|
| `MINIMAX_TTS_MODEL` | `speech-2.8-hd` | 最新 HD 模型，音色/韵律最佳；可选 `speech-2.8-turbo` / `speech-02-hd` 等 |
| `MINIMAX_TTS_VOICE_EN` | `male-qn-jingying` | 英文音色（男主播） |
| `MINIMAX_TTS_VOICE_ZH` | `female-shaonv` | 中文音色（女主播） |
| `MINIMAX_TTS_SPEED` | `1.0` | 语速 [0.5, 2] |
| `MINIMAX_TTS_MAX_CHARS` | `900` | 单请求文本长度，超长自动按句分块逐段合成再拼接 |
| `MINIMAX_TTS_GROUP_ID` | `""` | 可选；新版端点实测省略即可，旧账号/备用端点报缺 `GroupId` 时再填 |

常用音色：女主播 `female-shaonv` │ 成熟女声 `female-chengshu` │ 御姐 `female-yujie` │ 男主播 `male-qn-jingying` │ 青涩男声 `male-qn-qingse` │ 成熟男声 `male-chengshu`

## 技术选型

| 环节 | 方案 | 理由 |
|------|------|------|
| 提取 | stdlib `html.parser` + `zipfile` | EPUB 即 zip+xhtml，语义化 class 足够，无需重依赖 |
| 翻译 | LLM（默认 MiniMax）/ 百度文本翻译 v2 | LLM 译文达出版水准、保留 Markdown 结构；百度作低成本备选 |
| 解读 | 统一 LLM 客户端（默认 MiniMax） | 结构化 8 小节精读；thinking 块自动过滤、限流退避重试 |
| TTS | edge-tts（本地）/ MiniMax t2a_v2（云端 `TTS_PROVIDER` 切换） | 免费本地零成本；MiniMax 音色/韵律更佳；均幂等断点续传 |
| 导入 | Joplin Web Clipper API | 本地 HTTP，`:/resource_id` 内嵌音频 |

## 用法

### 0. 首次配置密钥

真实密钥放本地 `config_local.py`（已 `gitignore`，不入库），从模板复制后填写：

```bash
cp config_local.example.py config_local.py   # 填入: MINIMAX_API_KEY / SILICONFLOW_API_KEY / JOPLIN_TOKEN 等
```

MiniMax TTS 复用 `MINIMAX_API_KEY`，无需额外密钥；`GroupId` 新版端点可省略。

### 1. 提取整期（一次性）

```bash
python3 pipeline.py extract --epub TheEconomist.2026.08.22.epub \
  --workspace economist-2026-08-22        # 从 EPUB 解析出全部英文文章到 workspace/<期号>/articles/
```

### 2. 处理一篇文章（全流程串行）

`run` 严格走 翻译→解读→TTS 输入→音频→导入 五阶段，任一失败立即中止：

```bash
python3 pipeline.py run --num 1                        # 默认工作区
python3 pipeline.py run --num 1 --workspace other-2026-09-01   # 指定工作区
python3 pipeline.py run --num 1 --force                # 强制作废已产物重做
```

### 3. 整期一键（推荐）

`run_issue.py` 逐篇循环五阶段，**单篇失败不中断**，最后汇总报告；幂等可续跑：

```bash
python3 run_issue.py                                 # 处理整期全部
python3 run_issue.py --nums 1 5 12                   # 只处理指定几篇
python3 run_issue.py --workspace other-2026-09-01    # 换工作区/换期
python3 run_issue.py --force                         # 强制重做已有篇目
# 用 MiniMax 朗读整期：
TTS_PROVIDER=minimax python3 run_issue.py
```

### 4. 分阶段（可单跑/重跑某阶段）

每阶段支持 `--num N` 或 `--all`，需带上 `--workspace <期号>`（缺省为默认工作区）：

```bash
python3 pipeline.py translate --num 1 | --all        # 翻译
python3 pipeline.py analyze  --num 1 | --all [--force]  # LLM 中文解读
python3 pipeline.py prepare-tts --num 1 | --all      # 生成朗读输入
python3 pipeline.py tts --num 1 | --all [--workspace ...]  # 生成音频
python3 pipeline.py import --num 1 | --all [--force] [--watch]  # 导入 Joplin
# import --force: 已有笔记原地更新不产生重复
```

### 5. 用 MiniMax 生成语音（以「economist-2026-08-15 第 1 篇」为例）

```bash
# ① 生成朗读输入（en/zh_tr/zh_an 三个 md）
python3 pipeline.py prepare-tts --num 1 --workspace economist-2026-08-15
# ② 用 MiniMax 合成音频（输出到 workspace/.../audio/01/{en,zh_tr,zh_an}.mp3）
TTS_PROVIDER=minimax python3 pipeline.py tts --num 1 --workspace economist-2026-08-15
# 换音色/语速
MINIMAX_TTS_VOICE_ZH=female-chengshu TTS_PROVIDER=minimax \
  python3 pipeline.py tts --num 1 --workspace economist-2026-08-15
# 整期全部用 MiniMax
TTS_PROVIDER=minimax python3 pipeline.py tts --all --workspace economist-2026-08-15
```

> 提示：`--workspace` 传的是 `workspace/` 下的目录名；不传则用默认（`config.DEFAULT_WORKSPACE`）。提取/处理**新期号**时必须显式传 `--workspace`。

## 环境依赖

- Python 3.10+（主流程，**零第三方依赖**，stdlib 实现 HTTP）
- Joplin 桌面端开启 Web Clipper（`工具 → 选项 → Web Clipper`）
- TTS：
  - `TTS_PROVIDER=minimax`：仅需 MiniMax API Key（云端，无需本地引擎）
  - `TTS_PROVIDER=edge`（默认）：需 `/tmp/edge-tts-env`（可经 `MAGPIPE_TTS_PYTHON` 覆盖）及 `edge-tts`、`ffmpeg`
