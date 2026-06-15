"""
A2A 外部 Agent 客户端示例
展示一个真实 A2A Agent 如何接入中介平台

运行：
  # 1. 启动服务
  python -m zhongjie.api.app   # 或 uvicorn zhongjie.api.app:app

  # 2. 运行此脚本
  python examples/a2a_client_demo.py
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


PLATFORM_URL = "http://localhost:8000"


async def discover_platform(client: httpx.AsyncClient) -> dict:
    """Step 1: 通过 /.well-known/agent-card.json 发现平台"""
    r = await client.get(f"{PLATFORM_URL}/.well-known/agent-card.json")
    r.raise_for_status()
    card = r.json()
    print(f"📡 平台 Agent Card:")
    print(f"   名称: {card['name']}")
    print(f"   技能: {[s['id'] for s in card['skills']]}")
    return card


async def register_as_agent(client: httpx.AsyncClient) -> str:
    """Step 2: 注册当前 Agent（演示用）"""
    name = f"Demo-Headhunter-{uuid.uuid4().hex[:6]}"
    r = await client.post(f"{PLATFORM_URL}/api/agents", json={
        "name": name,
        "role": "headhunter",
        "capabilities": ["candidate_sourcing", "finance"],
    })
    r.raise_for_status()
    agent = r.json()
    print(f"\n✅ Agent 已注册: {agent['agent_id']}")
    print(f"   名称: {agent['name']}, 信任分: {agent['trust_score']}")
    return agent["agent_id"]


async def send_a2a_task(client: httpx.AsyncClient, kind: str, payload: dict,
                        context_id: str | None = None) -> dict:
    """Step 3: A2A 提交任务"""
    body = {
        "jsonrpc": "2.0", "id": f"req_{uuid.uuid4().hex[:6]}",
        "method": "tasks/send",
        "params": {
            "message": {
                "parts": [{"type": "data", "data": {"skill": kind, **payload}}],
            },
        },
    }
    if context_id:
        body["params"]["sessionId"] = context_id

    r = await client.post(f"{PLATFORM_URL}/a2a", json=body)
    r.raise_for_status()
    response = r.json()
    if "error" in response:
        raise RuntimeError(f"A2A error: {response['error']}")
    return response["result"]


async def query_a2a_task(client: httpx.AsyncClient, task_id: str) -> dict:
    """Step 4: A2A 查询任务状态"""
    r = await client.post(f"{PLATFORM_URL}/a2a", json={
        "jsonrpc": "2.0", "id": f"req_{uuid.uuid4().hex[:6]}",
        "method": "tasks/get",
        "params": {"id": task_id},
    })
    r.raise_for_status()
    return r.json()["result"]


async def stateles_message(client: httpx.AsyncClient) -> dict:
    """Step 5: A2A 无状态消息"""
    r = await client.post(f"{PLATFORM_URL}/a2a", json={
        "jsonrpc": "2.0", "id": "ping",
        "method": "message/send",
        "params": {
            "message": {
                "parts": [{"type": "data", "data": {"greeting": "hello from A2A client"}}],
            },
        },
    })
    r.raise_for_status()
    return r.json()["result"]


async def get_agent_card(client: httpx.AsyncClient, agent_id: str) -> dict:
    """Step 6: 获取特定 Agent 的 A2A Card"""
    r = await client.get(f"{PLATFORM_URL}/api/agents/{agent_id}/card")
    r.raise_for_status()
    return r.json()


async def main():
    print("=" * 60)
    print("🌐 A2A 外部 Agent 客户端 Demo")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. 发现平台
        await discover_platform(client)

        # 2. 注册自己
        my_agent_id = await register_as_agent(client)

        # 3. 无状态消息
        print("\n--- 无状态消息 (message/send) ---")
        result = await stateles_message(client)
        print(f"  Response: {json.dumps(result, ensure_ascii=False)[:200]}")

        # 4. 提交任务: 候选人寻访
        print("\n--- 提交任务 (tasks/send) ---")
        result = await send_a2a_task(
            client, kind="candidate_sourcing",
            payload={"jd": "高级金融工程师", "level": "P7", "salary": "50-80K"},
        )
        task_id = result["data"]["task_id"]
        print(f"  Task ID: {task_id}")
        print(f"  状态: {result['data']['state']}")

        # 5. 查询任务
        print("\n--- 查询任务 (tasks/get) ---")
        result = await query_a2a_task(client, task_id)
        print(f"  状态: {result['data']['state']}")

        # 6. 完成
        print("\n--- 完成任务 ---")
        r = await client.post(f"{PLATFORM_URL}/api/tasks/{task_id}/complete",
                              params={"result": "matched 3 candidates"})
        if r.status_code == 200:
            print(f"  ✅ Task 完成: {r.json()['state']}")
        else:
            print(f"  任务可能已自动完成: {r.status_code}")

        # 7. 查自己的 Agent Card
        print("\n--- 获取自己的 A2A Card ---")
        card = await get_agent_card(client, my_agent_id)
        print(f"  名称: {card['name']}")
        print(f"  能力: {[s['id'] for s in card['skills']]}")
        print(f"  信任分: {card['metadata']['trust_score']}")

    print("\n" + "=" * 60)
    print("✅ Demo 完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.ConnectError:
        print(f"\n❌ 连接失败: 请先启动服务")
        print(f"   uvicorn zhongjie.api.app:app --port 8000")
    except Exception as e:
        print(f"\n❌ 出错: {e}")
        import traceback
        traceback.print_exc()
