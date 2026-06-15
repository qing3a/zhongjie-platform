"""
L2 Identity - API Key + Token 认证层

历史: 老代码在根目录 auth.py (P1 M8 引入)，refactor 后迁入新 src 布局。
保持向后兼容: APIKey / Token / APIKeyManager 类签名不变，老的
``from auth import APIKeyManager`` 代码仍可在根目录运行时通过
``start.py --legacy`` 走老 api_server.py 路径。

新代码统一使用:
    from zhongjie.identity.auth import APIKeyManager, Token, require_role

设计:
- APIKey = key_id + sha256(secret) + 角色 + 权限 + agent_id(可选)
- Token = sha256(key_id_随机串_时间戳) → 内存字典
- 验签: HMAC-SHA256, 5 分钟时间窗
- 角色层级: admin > approver > requester > viewer
"""

from datetime import datetime, timedelta
import hashlib
import hmac
import logging
import time
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============ 模型 ============

class APIKey(BaseModel):
    key_id: str
    key_hash: str
    name: str
    role: str
    permissions: list[str] = []
    enabled: bool = True
    created_at: datetime
    expires_at: Optional[datetime] = None
    tenant_id: str = "default"
    agent_id: Optional[str] = None


class Token(BaseModel):
    token: str
    key_id: str
    role: str
    permissions: list[str] = []
    tenant_id: str = "default"
    expires_at: datetime
    agent_id: Optional[str] = None


# ============ 管理器 ============

class APIKeyManager:
    def __init__(self) -> None:
        self.keys: dict[str, APIKey] = {}
        self.tokens: dict[str, Token] = {}
        self._default_key: dict | None = None

    def generate_key_pair(
        self,
        name: str,
        role: str,
        days_valid: int = 30,
        tenant_id: str = "default",
        permissions: list[str] | None = None,
        agent_id: Optional[str] = None,
    ) -> dict:
        permissions = permissions or []
        key_id = f"ak_{uuid.uuid4().hex[:8]}"
        secret = uuid.uuid4().hex[:16]
        key_hash = hashlib.sha256(secret.encode()).hexdigest()

        api_key = APIKey(
            key_id=key_id, key_hash=key_hash, name=name, role=role,
            permissions=permissions, enabled=True, created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=days_valid),
            tenant_id=tenant_id, agent_id=agent_id,
        )
        self.keys[key_id] = api_key
        token = self._generate_token(key_id, role, tenant_id, days_valid, permissions, agent_id)
        return {
            "key_id": key_id, "secret": secret, "token": token, "role": role,
            "permissions": permissions, "name": name, "tenant_id": tenant_id,
            "agent_id": agent_id, "expires_at": api_key.expires_at.isoformat(),
        }

    def _generate_token(
        self, key_id: str, role: str, tenant_id: str = "default",
        days_valid: int = 30, permissions: list[str] | None = None,
        agent_id: Optional[str] = None,
    ) -> str:
        permissions = permissions or []
        token_str = f"{key_id}_{uuid.uuid4().hex}_{int(time.time())}"
        token_hash = hashlib.sha256(token_str.encode()).hexdigest()
        token = Token(
            token=token_hash, key_id=key_id, role=role,
            permissions=permissions, tenant_id=tenant_id,
            expires_at=datetime.now() + timedelta(days=days_valid),
            agent_id=agent_id,
        )
        self.tokens[token_hash] = token
        return token_hash

    def verify_token(self, token: str) -> Token | None:
        if token not in self.tokens:
            return None
        t = self.tokens[token]
        if not t or not t.expires_at or datetime.now() > t.expires_at:
            return None
        if t.key_id not in self.keys:
            return None
        key = self.keys[t.key_id]
        if not key.enabled or (key.expires_at and datetime.now() > key.expires_at):
            return None
        if key.permissions:
            t.permissions = key.permissions
        # 同步 agent_id: key 是 agent 身份的唯一权威, 实时覆盖 token 上的值
        # 旧版"只填不覆盖"会导致: key 重绑到新 agent 后, 老 token 仍以旧 agent 身份操作 → 越权
        t.agent_id = key.agent_id
        return t

    def verify_signature(self, key_id: str, signature: str, timestamp: str, body: str = "") -> bool:
        if key_id not in self.keys:
            return False
        key = self.keys[key_id]
        if not key.enabled:
            return False
        try:
            req_time = int(timestamp)
            now = int(time.time())
            if abs(now - req_time) > 300:
                return False
        except ValueError:
            return False
        message = f"{key_id}_{timestamp}_{body}"
        expected = hmac.new(
            key.key_hash.encode(), message.encode(), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def revoke_key(self, key_id: str) -> bool:
        if key_id in self.keys:
            self.keys[key_id].enabled = False
            return True
        return False

    def revoke_token(self, token: str) -> bool:
        if token in self.tokens:
            del self.tokens[token]
            return True
        return False

    def list_keys(self, role: str | None = None) -> list[dict]:
        result = []
        for k in self.keys.values():
            if role and k.role != role:
                continue
            result.append({
                "key_id": k.key_id, "name": k.name, "role": k.role,
                "permissions": k.permissions, "enabled": k.enabled,
                "created_at": k.created_at.isoformat(),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            })
        return result

    def get_key(self, key_id: str) -> dict | None:
        k = self.keys.get(key_id)
        if not k:
            return None
        return {
            "key_id": k.key_id, "name": k.name, "role": k.role,
            "permissions": k.permissions, "enabled": k.enabled,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "tenant_id": k.tenant_id,
        }

    def update_key(
        self, key_id: str, name: str | None = None, role: str | None = None,
        permissions: list | None = None, enabled: bool | None = None,
    ) -> dict | None:
        k = self.keys.get(key_id)
        if not k:
            return None
        if name is not None: k.name = name
        if role is not None: k.role = role
        if permissions is not None: k.permissions = permissions
        if enabled is not None: k.enabled = enabled
        return {
            "key_id": k.key_id, "name": k.name, "role": k.role,
            "permissions": k.permissions, "enabled": k.enabled,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        }

    def delete_key(self, key_id: str) -> bool:
        if key_id in self.keys:
            del self.keys[key_id]
            return True
        return False

    def get_default_key(self) -> dict:
        """获取默认测试 Key（仅开发用）"""
        if self._default_key is None:
            self._default_key = self.generate_key_pair(
                name="测试密钥", role="admin", days_valid=365, tenant_id="default",
            )
        return self._default_key


# ============ 角色层级 ============

ROLE_LEVELS: dict[str, int] = {
    "admin": 4, "approver": 3, "requester": 2, "viewer": 1,
}

ROLES: dict[str, str] = {
    "admin": "完全访问权限",
    "approver": "审批权限（可审批请求）",
    "requester": "请求权限（可提交请求、查看状态）",
    "viewer": "只读权限（仅查看数据）",
}

PERMISSIONS: dict[str, str] = {
    "headhunter_submit_jd": "提交 JD",
    "headhunter_submit_candidate": "提交候选人",
    "headhunter_submit_match": "提交匹配",
    "company_view_matches": "查看匹配列表",
    "company_reply_interview": "回复面试",
    "platform_approve": "审批通过",
    "platform_reject": "审批拒绝",
    "platform_manage_rules": "管理规则",
}


def check_permission(token: Token, required_role: str) -> bool:
    user_level = ROLE_LEVELS.get(token.role, 0)
    required_level = ROLE_LEVELS.get(required_role, 0)
    return user_level >= required_level


def has_permission(token: Token, permission: str) -> bool:
    if not token:
        return False
    if token.role == "admin":
        return True
    return permission in token.permissions


# ============ FastAPI 依赖 ============

token_header = APIKeyHeader(name="Authorization", auto_error=False)


def get_current_token(
    token: Optional[str] = Security(token_header),
    key_manager: APIKeyManager | None = None,
) -> Token:
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    if not key_manager:
        raise HTTPException(status_code=500, detail="Auth not configured")
    t = key_manager.verify_token(token)
    if not t:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return t


def require_role(required_role: str, security_manager=None, client_ip=None):
    def dependency(token: Token = Depends(get_current_token)) -> Token:
        if not check_permission(token, required_role):
            if security_manager:
                security_manager.log(
                    event="permission_denied",
                    key_id=token.key_id if token else None,
                    ip=client_ip,
                    detail=f"requires {required_role} role",
                )
            raise HTTPException(status_code=403, detail=f"Requires {required_role} role")
        return token
    return dependency


def require_permission(permission: str):
    def dependency(token: Token = Depends(get_current_token)) -> Token:
        if not has_permission(token, permission):
            raise HTTPException(status_code=403, detail=f"Requires permission: {permission}")
        return token
    return dependency


# ============ Demo ============

if __name__ == "__main__":
    km = APIKeyManager()
    print("=" * 50)
    print("API Key 管理器演示 (zhongjie.identity.auth)")
    print("=" * 50)
    result = km.generate_key_pair(name="猎头客户端", role="requester")
    print(f"\n生成密钥对:")
    print(f"  key_id: {result['key_id']}")
    print(f"  secret: {result['secret']}")
    print(f"  token:  {result['token'][:20]}...")
    token = km.verify_token(result['token'])
    print(f"\n验证 Token: {token.role if token else '失败'}")
    print(f"\n权限检查:")
    print(f"  requester -> approver: {check_permission(token, 'approver') if token else 'N/A'}")
