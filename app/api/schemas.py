"""数据模式占位定义。"""

from dataclasses import dataclass


@dataclass(slots=True)
class RunRequest:
    task: str


@dataclass(slots=True)
class RunResponse:
    status: str
    detail: str
