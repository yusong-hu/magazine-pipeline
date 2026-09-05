"""轻量 HTTP 客户端 — 基于 stdlib urllib，零第三方依赖。

全流水线（Joplin / 百度翻译 / LLM）统一经此模块发请求，
不依赖 requests，任何 Python >= 3.8 环境可直接运行。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional


class HTTPError(Exception):
    """非 2xx 响应，携带 status 与原始 body 文本。"""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:300]}")


def request(method: str, url: str, *, params: Optional[dict] = None,
            json_body=None, data: Optional[bytes] = None,
            headers: Optional[dict] = None, timeout: int = 120) -> tuple:
    """发起 HTTP 请求，返回 (status, text)。非 2xx 抛 HTTPError。"""
    if params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urllib.parse.urlencode(params)}"
    req_headers = {"User-Agent": "magazine-pipeline/1.0"}
    if headers:
        req_headers.update(headers)
    body = data
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=req_headers,
                                 method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise HTTPError(e.code, e.read().decode("utf-8", errors="replace")) from None


def _loads(text: str) -> dict:
    return json.loads(text) if text.strip() else {}


def get_json(url: str, **kwargs) -> dict:
    _, text = request("GET", url, **kwargs)
    return _loads(text)


def post_json(url: str, payload, **kwargs) -> dict:
    _, text = request("POST", url, json_body=payload, **kwargs)
    return _loads(text)


def put_json(url: str, payload, **kwargs) -> dict:
    _, text = request("PUT", url, json_body=payload, **kwargs)
    return _loads(text)


def post_multipart(url: str, *, params: Optional[dict] = None, fields: dict,
                   file_field: str, file_path: Path, file_mime: str,
                   headers: Optional[dict] = None, timeout: int = 300) -> dict:
    """multipart/form-data 上传文件（用于 Joplin 资源）。"""
    if params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urllib.parse.urlencode(params)}"
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        .encode("utf-8"))
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{file_path.name}"\r\n'
        f"Content-Type: {file_mime}\r\n\r\n"
    .encode("utf-8"))
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req_headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if headers:
        req_headers.update(headers)
    _, text = request("POST", url, data=body, headers=req_headers, timeout=timeout)
    return _loads(text)
