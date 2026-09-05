"""TTS 音频生成 — 调用本地 text-to-speech 引擎，逐篇生成 en/zh_tr/zh_an 音频。

用法:
    python -m tts.generate_audio --num 1 [--workspace xxx]
    python -m tts.generate_audio --all

特性: 已存在且非空的音频自动跳过；引擎自身支持断点续传（state 文件）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.contract import Workspace, get_workspace

KIND_VOICE = {"en": config.VOICE_EN, "zh_tr": config.VOICE_ZH, "zh_an": config.VOICE_ZH}

# macOS 上 IDE 注入的 __PYVENV_LAUNCHER__ 会破坏 venv 解释器的路径解析
TTS_ENV = {k: v for k, v in __import__("os").environ.items()
           if k not in ("__PYVENV_LAUNCHER__", "PYTHONHOME", "PYTHONSTARTUP")}


def generate_audio(ws: Workspace, num: int) -> dict[str, bool]:
    """为一篇文章生成 3 个音频，返回 {kind: 成功与否}。"""
    results = {}
    for kind, voice in KIND_VOICE.items():
        src = ws.tts_input(num, kind)
        out = ws.audio(num, kind)
        results[kind] = False

        if not src.exists() or not src.stat().st_size:
            print(f"  [{num:02d}] {kind}: 无输入，跳过")
            continue
        if out.exists() and out.stat().st_size > 0:
            print(f"  [{num:02d}] {kind}: 已存在，跳过")
            results[kind] = True
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            config.TTS_PYTHON, str(config.TTS_ENGINE),
            "--input", str(src),
            "--output", str(out),
            "--voice", voice,
            "--cooldown", str(config.TTS_COOLDOWN),
            "--max-chars", str(config.TTS_MAX_CHARS),
            "--state-file", str(ws.audio_state(num, kind)),
        ]
        print(f"  [{num:02d}] {kind}: 生成中 (voice={voice})...", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=TTS_ENV)
        if proc.returncode != 0:
            print(f"  [{num:02d}] {kind}: 失败\n{proc.stderr[-500:]}")
            continue
        # 从引擎输出中提取时长
        dur = ""
        for line in proc.stderr.splitlines():
            if "duration:" in line:
                dur = line.split("duration:")[-1].strip()
                break
        print(f"  [{num:02d}] {kind}: 完成 {dur}")
        results[kind] = True
    return results


def main():
    ap = argparse.ArgumentParser(description="批量生成 TTS 音频")
    ap.add_argument("--num", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    for num in nums:
        print(f"[{num:02d}] 开始 TTS")
        generate_audio(ws, num)
    print(f"\n音频目录: {ws.audio_dir}")


if __name__ == "__main__":
    main()
