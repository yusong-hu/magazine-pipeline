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

KIND_EDGE_VOICE = {"en": config.VOICE_EN, "zh_tr": config.VOICE_ZH, "zh_an": config.VOICE_ZH}
KIND_MINIMAX_VOICE = {
    "en": config.MINIMAX_TTS_VOICE_EN,
    "zh_tr": config.MINIMAX_TTS_VOICE_ZH,
    "zh_an": config.MINIMAX_TTS_VOICE_ZH,
}


def _voice_map() -> dict[str, str]:
    """按 TTS_PROVIDER 返回 kind → voice 映射。"""
    if config.TTS_PROVIDER == "minimax":
        return KIND_MINIMAX_VOICE
    return KIND_EDGE_VOICE


# macOS 上 IDE 注入的 __PYVENV_LAUNCHER__ 会破坏 venv 解释器的路径解析
TTS_ENV = {k: v for k, v in __import__("os").environ.items()
           if k not in ("__PYVENV_LAUNCHER__", "PYTHONHOME", "PYTHONSTARTUP")}


def _synth_minimax(ws: Workspace, num: int, kind: str, src: Path) -> float:
    """用 MiniMax TTS 合成单 kind 音频，返回时长（秒）。"""
    from tts.minimax_tts import synth_mp3
    out = ws.audio(num, kind)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8", errors="replace")
    dur = synth_mp3(text, out, _voice_map()[kind],
                    on_chunk=lambda i, n, ms: print(
                        f"    [{num:02d}] {kind}: 块 {i}/{n} ({ms/1000:.1f}s)",
                        flush=True))
    print(f"  [{num:02d}] {kind}: 完成 时长 {dur:.1f}s {out}")
    return dur


def _synth_edge(ws: Workspace, num: int, kind: str, src: Path) -> bool:
    """用本地 edge 引擎合成单 kind 音频，返回是否成功。"""
    out = ws.audio(num, kind)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        config.TTS_PYTHON, str(config.TTS_ENGINE),
        "--input", str(src),
        "--output", str(out),
        "--voice", _voice_map()[kind],
        "--cooldown", str(config.TTS_COOLDOWN),
        "--max-chars", str(config.TTS_MAX_CHARS),
        "--state-file", str(ws.audio_state(num, kind)),
    ]
    print(f"  [{num:02d}] {kind}: 生成中 (voice={_voice_map()[kind]})...", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=TTS_ENV)
    if proc.returncode != 0:
        print(f"  [{num:02d}] {kind}: 失败\n{proc.stderr[-500:]}")
        return False
    dur = ""
    for line in proc.stderr.splitlines():
        if "duration:" in line:
            dur = line.split("duration:")[-1].strip()
            break
    print(f"  [{num:02d}] {kind}: 完成 {dur}")
    return True


def generate_audio(ws: Workspace, num: int) -> dict[str, bool]:
    """为一篇文章生成 3 个音频，返回 {kind: 成功与否}。"""
    results = {}
    for kind in _voice_map():
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

        if config.TTS_PROVIDER == "minimax":
            try:
                _synth_minimax(ws, num, kind, src)
                results[kind] = True
            except Exception as e:
                print(f"  [{num:02d}] {kind}: MiniMax 合成失败 {type(e).__name__}: {e}")
        else:
            results[kind] = _synth_edge(ws, num, kind, src)
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
