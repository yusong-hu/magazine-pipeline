"""Joplin Web API 客户端 — 全项目唯一的 Joplin 访问封装。"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Optional

import requests

import config


class JoplinClient:
    def __init__(self, base: str = None, token: str = None):
        self.base = base or config.JOPLIN_BASE
        self.token = token or config.JOPLIN_TOKEN

    # ---------- 基础请求 ----------
    def request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base}{path}"
        params = kwargs.pop("params", {})
        params["token"] = self.token
        r = requests.request(method, url, params=params, timeout=120, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f"Joplin API {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    # ---------- 笔记本 ----------
    def resolve_notebook_id(self, name: Optional[str] = None) -> str:
        """优先用配置 ID；否则按名称查找/创建，不存在则创建。

        name 缺省时用 config.JOPLIN_NOTEBOOK_NAME；调用方通常传工作区同名。
        """
        if config.JOPLIN_NOTEBOOK_ID:
            return config.JOPLIN_NOTEBOOK_ID
        n = name or config.JOPLIN_NOTEBOOK_NAME
        folders = self.request("GET", "/folders",
                               params={"fields": "id,title", "limit": 100})
        for f in folders.get("items", []):
            if f["title"] == n:
                return f["id"]
        created = self.request("POST", "/folders",
                               json={"title": n})
        return created["id"]

    # ---------- 笔记 ----------
    def find_note_by_title(self, title: str) -> Optional[str]:
        r = self.request("GET", "/notes",
                         params={"query": f'"{title}"', "fields": "id,title", "limit": 10})
        for n in r.get("items", []):
            if n.get("title") == title:
                return n["id"]
        return None

    def create_note(self, notebook_id: str, title: str, body: str) -> str:
        result = self.request("POST", "/notes", json={
            "parent_id": notebook_id,
            "title": title,
            "body": body,
            "source": "markdown",
        })
        return result["id"]

    def update_note(self, note_id: str, body: str, title: str | None = None) -> None:
        payload = {"body": body}
        if title:
            payload["title"] = title
        self.request("PUT", f"/notes/{note_id}", json=payload)

    # ---------- 资源 ----------
    def upload_resource(self, file_path: Path) -> str:
        mime, _ = mimetypes.guess_type(str(file_path))
        if not mime:
            mime = "audio/mpeg"
        props = json.dumps({"filename": file_path.name, "mime": mime})
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{self.base}/resources",
                params={"token": self.token},
                files={"data": (file_path.name, f, mime)},
                data={"props": props},
                timeout=300,
            )
        if r.status_code >= 400:
            raise RuntimeError(f"资源上传失败 {r.status_code}: {r.text[:300]}")
        result = r.json()
        if "error" in result:
            raise RuntimeError(f"资源上传失败: {result['error']}")
        return result["id"]
