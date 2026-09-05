"""路径与命名契约 — 各阶段之间文件传递的唯一规则来源。

任何阶段需要读/写另一阶段产出的文件，必须经由 Workspace 提供的方法，
禁止在业务代码中手工拼接路径。

目录布局（workspace/<name>/）:
  articles/      NN_slug.md          英文原文（提取阶段产出）
  articles-zh/   NN_zh.md           中文翻译（翻译阶段产出）
  tts_inputs/    NN_tts/01_en.md    TTS 输入（预处理阶段产出）
  audio/         NN/en|zh_tr|zh_an.mp3  音频（TTS 阶段产出）
  .state/        各阶段断点状态
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import config


class Workspace:
    """一个杂志期刊的完整工作区。"""

    def __init__(self, name: str, root: Optional[Path] = None):
        self.name = name
        self.root = (root or config.WORKSPACE_ROOT) / name

    # ---------- 目录 ----------
    @property
    def articles_dir(self) -> Path:
        return self.root / "articles"

    @property
    def zh_dir(self) -> Path:
        return self.root / "articles-zh"

    @property
    def tts_inputs_dir(self) -> Path:
        return self.root / "tts_inputs"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def state_dir(self) -> Path:
        return self.root / ".state"

    def ensure_dirs(self) -> None:
        for d in (self.articles_dir, self.zh_dir, self.tts_inputs_dir,
                  self.audio_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---------- 文章文件 ----------
    def en_md(self, num: int) -> Optional[Path]:
        """按编号找英文原文，如 01_the-world-this-week.md"""
        matches = sorted(self.articles_dir.glob(f"{num:02d}_*.md"))
        return matches[0] if matches else None

    def zh_md(self, num: int) -> Path:
        return self.zh_dir / f"{num:02d}_zh.md"

    def all_en_nums(self) -> list[int]:
        nums = []
        for p in self.articles_dir.glob("*.md"):
            m = re.match(r"^(\d+)_", p.stem)
            if m:
                nums.append(int(m.group(1)))
        return sorted(nums)

    # ---------- TTS 输入 / 音频 ----------
    def tts_input_dir(self, num: int) -> Path:
        return self.tts_inputs_dir / f"{num:02d}_tts"

    def tts_input(self, num: int, kind: str) -> Path:
        names = {"en": "01_en.md", "zh_tr": "02_zh_tr.md", "zh_an": "03_zh_an.md"}
        return self.tts_input_dir(num) / names[kind]

    def audio(self, num: int, kind: str) -> Path:
        names = {"en": "en.mp3", "zh_tr": "zh_tr.mp3", "zh_an": "zh_an.mp3"}
        return self.audio_dir / f"{num:02d}" / names[kind]

    def audio_state(self, num: int, kind: str) -> Path:
        return self.audio_dir / f"{num:02d}" / f".{kind}-state.json"

    # ---------- 状态 ----------
    def state_file(self, name: str) -> Path:
        return self.state_dir / f"{name}.json"


def get_workspace(name: Optional[str] = None) -> Workspace:
    ws = Workspace(name or config.DEFAULT_WORKSPACE)
    ws.ensure_dirs()
    return ws
