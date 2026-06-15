"""
脱敏工具 - 从 api_server.py:1215-1244 抽出
保持原有逻辑不变，零行为差异
"""
from typing import Any


# 默认脱敏配置（与老 _masking_config 同形）
DEFAULT_MASKING_CONFIG: dict[str, dict] = {
    "salary": {"enabled": True, "level": "partial", "fields": ["expected_salary"]},
    "id_card": {"enabled": True, "level": "partial", "fields": ["id_card"]},
    "bank_card": {"enabled": True, "level": "partial", "fields": ["bank_card"]},
    "phone": {"enabled": True, "level": "mask", "fields": ["phone"]},
    "email": {"enabled": True, "level": "mask", "fields": ["email"]},
    "name": {"enabled": True, "level": "mask", "fields": ["name", "candidate_name"]},
}


def mask_salary(value: str, level: str = "partial") -> str:
    """薪资脱敏: 30-50K -> 30-50K (partial 保持区间)/ **-**K (mask)"""
    if level == "mask":
        return "**K"
    # partial: 保留区间端点
    return value


def mask_id_card(value: str, level: str = "partial") -> str:
    if not value or len(value) < 4:
        return value
    if level == "mask":
        return "****"
    return value[:4] + "**********"


def mask_bank_card(value: str, level: str = "partial") -> str:
    if not value or len(value) < 4:
        return value
    return "****" + value[-4:]


def mask_phone(value: str) -> str:
    if not value or len(value) < 7:
        return value
    return value[:3] + "****" + value[-4:]


def mask_email(value: str) -> str:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if not local:
        return value
    return local[0] + "***@" + domain


def mask_sensitive_data(data: dict, config: dict | None = None) -> dict:
    """脱敏敏感字段（与 api_server.py:1222-1244 行为一致）"""
    cfg = config or DEFAULT_MASKING_CONFIG
    result = data.copy()
    for field_name, conf in cfg.items():
        if not conf.get("enabled", False):
            continue
        level = conf.get("level", "mask")
        target_fields = conf.get("fields", [field_name])
        for target_field in target_fields:
            if target_field in result and result[target_field]:
                if field_name == "salary":
                    result[target_field] = mask_salary(str(result[target_field]), level)
                elif field_name == "id_card":
                    result[target_field] = mask_id_card(result[target_field], level)
                elif field_name == "bank_card":
                    result[target_field] = mask_bank_card(result[target_field], level)
                elif field_name == "phone":
                    result[target_field] = mask_phone(result[target_field])
                elif field_name == "email":
                    result[target_field] = mask_email(result[target_field])
                elif field_name == "name":
                    name = result[target_field]
                    result[target_field] = (name[:1] + "*") if name else name
    return result
