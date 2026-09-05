"""MiniMax TTS 语音合成 — 调用 t2a_v2 接口生成 mp3。

长文本按句分块逐段合成，按序拼接为一个 mp3 文件；单块限流/出错自动退避重试。
复用 config.MINIMAX_API_KEY 与 core/http.py，零第三方依赖。

用法（供 tts/generate_audio.py 在 TTS_PROVIDER=minimax 时调用）:
    from tts.minimax_tts import synth_mp3
    duration = synth_mp3("中文文本…", out_path, voice="female-shaonv")
"""
from __future__ import annotations

import base64
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.http import HTTPError, post_json

_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s*")


def _decode_audio(audio: str) -> bytes:
    """解码 t2a_v2 返回的 audio 字段。

    官方（非流式）返回十六进制字符串；旧版/部分端点返回 base64。
    先按 hex 解码，失败再回退 base64，二者兼容。
    """
    audio = (audio or "").strip()
    if not audio:
        return b""
    try:
        return bytes.fromhex(audio)
    except ValueError:
        return base64.b64decode(audio)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """按句粒度切块，保证单块不超 max_chars（长句硬切）。"""
    text = text.strip()
    if not text:
        return []
    sents = [s for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sents:
        sents = [text]
    chunks, cur = [], ""
    for s in sents:
        # 单句自身超限 → 直接整体硬切
        while len(s) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(s[:max_chars])
            s = s[max_chars:]
        if len(cur) + len(s) <= max_chars:
            cur += s
        else:
            if cur:
                chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks


def _synth_chunk(text: str, voice: str, *, retries: int) -> tuple[int, bytes]:
    """合成单块文本，返回 (时长ms, mp3二进制)。限流/错误时退避重试。"""
    url = (f"{config.MINIMAX_TTS_BASE_URL}/v1/t2a_v2"
           f"?GroupId={config.MINIMAX_TTS_GROUP_ID}")
    payload = {
        "model": config.MINIMAX_TTS_MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": voice, "speed": config.MINIMAX_TTS_SPEED},
        "audio_setting": {"sample_rate": 32000, "bit_rate": 128000,
                          "format": "mp3", "channel": 1},
    }
    headers = {"Authorization": f"Bearer {config.MINIMAX_API_KEY}"}
    for attempt in range(retries + 1):
        try:
            resp = post_json(url, payload, headers=headers,
                             timeout=config.MINIMAX_TTS_TIMEOUT)
            base = resp.get("base_resp", {})
            code = base.get("status_code", 0)
            if code != 0:
                raise RuntimeError(f"MiniMax TTS {code}: {base.get('status_msg')}")
            data = resp.get("data", {})
            audio = _decode_audio(data.get("audio"))
            if not audio:
                raise RuntimeError("MiniMax TTS: 响应缺少/为空 audio 字段")
            # 时长毫秒：extra_info.audio_length 或 data.audio_length
            ext = resp.get("extra_info", {}) or {}
            length = ext.get("audio_length") or data.get("audio_length") or 0
            return int(length), audio
        except HTTPError as e:
            if e.status == 429 and attempt < retries:
                time.sleep(config.MINIMAX_TTS_RETRY_WAIT)
                continue
            raise
        except RuntimeError:
            if attempt < retries:
                time.sleep(config.MINIMAX_TTS_RETRY_WAIT)
                continue
            raise
    raise RuntimeError("MiniMax TTS: 重试耗尽")


def synth_mp3(text: str, out: Path, voice: str, *, on_chunk=None) -> float:
    """将整段文本合成为 mp3 文件，返回总时长（秒）。"""
    chunks = _chunk_text(text, config.MINIMAX_TTS_MAX_CHARS)
    if not chunks:
        raise ValueError("输入文本为空")
    total_ms = 0
    with open(out, "wb") as f:
        for i, c in enumerate(chunks, 1):
            ms, data = _synth_chunk(c, voice,
                                    retries=config.MINIMAX_TTS_MAX_RETRIES)
            f.write(data)
            total_ms += ms
            if on_chunk:
                on_chunk(i, len(chunks), ms)
    return total_ms / 1000.0