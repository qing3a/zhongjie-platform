"""
规则定义 - 从 p0_core.py:108-121 抽出
所有 conditions 命中才匹配，按 priority 排序
"""
from .conditions import Condition
from .models import ActionType, Request


class Rule:
    """规则
    对应老 p0_core.py:108-121
    """

    def __init__(
        self,
        id: str,
        name: str,
        conditions: list[Condition],
        action: ActionType,
        priority: int = 0,
        enabled: bool = True,
    ):
        self.id = id
        self.name = name
        self.conditions = conditions
        self.action = action
        self.priority = priority
        self.enabled = enabled

    def match(self, request: Request) -> bool:
        if not self.enabled:
            return False
        return all(c.match(request) for c in self.conditions)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.value,
            "priority": self.priority,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(
            id=data["id"],
            name=data["name"],
            conditions=[Condition.from_dict(c) for c in data.get("conditions", [])],
            action=ActionType(data["action"]),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
        )
