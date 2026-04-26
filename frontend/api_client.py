"""HTTP + SSE 客户端。

后端契约（来自 EZ_AGENT_CODEX_GUIDE）：
  POST /api/v1/research                    -> 创建会话（不启动 graph）
  GET  /api/v1/research/stream/{sid}       -> SSE 流（首连时原子抢占启动）
  GET  /api/v1/research/{sid}              -> 会话详情
  GET  /api/v1/research                    -> 历史会话列表
  GET  /health                             -> 健康检查

SSE 事件类型：stage / sub_questions / searching / reading / critic /
              writing / done / error

设计要点：
1. 流式接口返回生成器，由调用方驱动，不自行 spawn 线程；
2. 每条事件都假定带有 event_id（修正 11.1：自增整数主键），
   断线重连时通过 last_event_id 续接；
3. 网络异常透传给上层，由 UI 决定重试策略。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

import httpx


def _parse_event_id(value: Any) -> int | None:
    """Parse an SSE id field without breaking the stream on malformed input."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------
# 异常
# ----------------------------------------------------------------------

class ApiError(Exception):
    """API 调用失败。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ----------------------------------------------------------------------
# 客户端
# ----------------------------------------------------------------------

class EzAgentClient:
    """同步 httpx 客户端 + 手写 SSE 解析器。

    Streamlit 的执行模型是同步的，因此这里不引入 asyncio。
    SSE 解析器手工实现，避免引入 `httpx-sse` 依赖。
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """探活。返回 {"status": "ok"} 或抛 ApiError。"""
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5.0)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ApiError(f"健康检查失败：{exc}") from exc

    # ------------------------------------------------------------------
    # 创建研究会话
    # ------------------------------------------------------------------
    def create_research(
        self,
        query: str,
        *,
        language: Literal["zh", "en"] = "zh",
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        """POST /api/v1/research

        返回 {session_id, status:"created", stream_url, created_at}。
        """
        payload = {
            "query": query,
            "language": language,
            "max_iterations": max_iterations,
        }
        try:
            r = httpx.post(
                f"{self.base_url}/api/v1/research",
                json=payload,
                timeout=self._timeout,
            )
            if r.status_code >= 400:
                detail = self._extract_error(r)
                raise ApiError(detail, status_code=r.status_code)
            return r.json()
        except httpx.HTTPError as exc:
            raise ApiError(f"创建研究会话失败：{exc}") from exc

    # ------------------------------------------------------------------
    # 拉取会话详情 / 列表
    # ------------------------------------------------------------------
    def get_session(self, session_id: str) -> dict[str, Any] | None:
        try:
            r = httpx.get(
                f"{self.base_url}/api/v1/research/{session_id}",
                timeout=self._timeout,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ApiError(f"获取会话失败：{exc}") from exc

    def list_sessions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        try:
            r = httpx.get(
                f"{self.base_url}/api/v1/research",
                params={"limit": limit},
                timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
            # 兼容 {"items":[...]} 与裸 list 两种返回
            return data.get("items", data) if isinstance(data, dict) else data
        except httpx.HTTPError as exc:
            raise ApiError(f"获取会话列表失败：{exc}") from exc

    # ------------------------------------------------------------------
    # SSE 订阅
    # ------------------------------------------------------------------
    def stream_events(
        self,
        session_id: str,
        *,
        last_event_id: int = 0,
    ) -> Iterator[dict[str, Any]]:
        """连接 SSE 流，逐事件 yield。

        生成的事件 dict 形如：
          {"type": "stage", "data": {...}, "event_id": 42}

        协议要点：
          - SSE 格式：每条事件由若干 `field: value\\n` 行组成，空行结束；
          - 我们读取 `event:` 作为 type，`data:` 作为 JSON payload，
            `id:` 作为 event_id（若服务端写入）；
          - 修正 11.4 算法：服务端会先重放历史，后续 live 事件可能与
            历史重复，由调用方按 event_id 去重。
        """
        url = f"{self.base_url}/api/v1/research/stream/{session_id}"
        params = {"after_event_id": last_event_id} if last_event_id > 0 else None
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if last_event_id > 0:
            # 标准 SSE 重连机制
            headers["Last-Event-ID"] = str(last_event_id)

        # SSE 是长连接，禁用读超时；连接超时仍保留
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)

        try:
            with httpx.stream(
                "GET",
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as r:
                if r.status_code >= 400:
                    body = b"".join(r.iter_bytes()).decode("utf-8", "replace")
                    raise ApiError(
                        f"SSE 连接失败 (HTTP {r.status_code}): {body[:200]}",
                        status_code=r.status_code,
                    )
                yield from self._parse_sse(r.iter_lines())
        except httpx.HTTPError as exc:
            raise ApiError(f"SSE 流中断：{exc}") from exc

    # ------------------------------------------------------------------
    # 内部：SSE 行解析
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_sse(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
        """把原始 SSE 行流解析为事件 dict。

        实现：维护 `current` 字典累积字段，遇到空行 flush 一条事件。
        """
        current: dict[str, Any] = {}
        data_buf: list[str] = []

        for raw in lines:
            line = raw.rstrip("\r")

            if line == "":
                # 事件分隔
                if data_buf or current:
                    payload_str = "\n".join(data_buf)
                    parsed: Any = None
                    if payload_str:
                        try:
                            parsed = json.loads(payload_str)
                        except json.JSONDecodeError:
                            parsed = {"raw": payload_str}
                    yield {
                        "type": current.get("event", "message"),
                        "data": parsed if isinstance(parsed, dict) else {"value": parsed},
                        "event_id": _parse_event_id(current.get("id")),
                    }
                current = {}
                data_buf = []
                continue

            if line.startswith(":"):
                # 注释行（keep-alive）
                continue

            if ":" in line:
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
            else:
                field, value = line, ""

            if field == "data":
                data_buf.append(value)
            elif field in {"event", "id", "retry"}:
                current[field] = value

        # 流结束时若仍有残留，flush 一次
        if data_buf or current:
            payload_str = "\n".join(data_buf)
            if payload_str:
                try:
                    parsed = json.loads(payload_str)
                except json.JSONDecodeError:
                    parsed = {"raw": payload_str}
            else:
                parsed = {}
            yield {
                "type": current.get("event", "message"),
                "data": parsed if isinstance(parsed, dict) else {"value": parsed},
                "event_id": _parse_event_id(current.get("id")),
            }

    # ------------------------------------------------------------------
    # 内部：错误体提取
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                return str(
                    data.get("detail")
                    or data.get("message")
                    or data.get("error")
                    or data
                )
            return str(data)
        except (ValueError, TypeError):
            return response.text[:200] or f"HTTP {response.status_code}"
