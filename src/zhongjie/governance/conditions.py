"""
规则条件 - 从 p0_core.py:59-106 抽出
支持嵌套字段路径（payload.amount / payload.jd.level）
"""
from typing import Any

from .models import Request


# 支持的操作符集合
SUPPORTED_OPS = {"==", "!=", ">", "<", "in", "not_in", "contains"}


class Condition:
    """规则条件
    对应老 p0_core.py:59-106
    行为完全一致：通过 _get_field_value 支持嵌套字段
    """

    def __init__(self, field: str, op: str, value: Any):
        if op not in SUPPORTED_OPS:
            raise ValueError(f"Unsupported op: {op}. Must be one of {SUPPORTED_OPS}")
        self.field = field
        self.op = op
        self.value = value

    def match(self, request: Request) -> bool:
        field_value = self._get_field_value(request, self.field)
        if field_value is None:
            return False
        if self.op == "==":
            return field_value == self.value
        if self.op == "!=":
            return field_value != self.value
        if self.op == ">":
            return field_value > self.value
        if self.op == "<":
            return field_value < self.value
        if self.op == "in":
            return field_value in self.value
        if self.op == "not_in":
            return field_value not in self.value
        if self.op == "contains":
            return self.value in str(field_value)
        return False

    def _get_field_value(self, request: Request, field: str) -> Any:
        """从 request 中获取字段值，支持嵌套
        优先从 request 顶层取（如 source/target/intent），
        否则当路径从 'payload.' 开头或未在顶层时从 payload 解析
        """
        parts = field.split(".")
        # 先尝试从 request 顶层获取
        if hasattr(request, parts[0]):
            value = getattr(request, parts[0])
            if value is None:
                # 字段为 None（如 owner_agent_id 缺省）→ 走 payload 路径
                pass
            else:
                for part in parts[1:]:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        return None
                return value
        # 从 payload 中获取
        value = request.payload
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def to_dict(self) -> dict:
        return {"field": self.field, "op": self.op, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict) -> "Condition":
        return cls(field=data["field"], op=data["op"], value=data["value"])
