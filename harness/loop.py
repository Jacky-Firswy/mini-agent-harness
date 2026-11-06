"""回合循环。

对应 ORG2 里的 `agent_core::core::turn_executor`（`mod.rs` 的 execute_turn）。

整个 Agent 的智能感，八成来自这个循环：

    请求模型 → 模型说要用工具 → 执行工具 → 把结果喂回去 → 再请求模型 → ...

直到模型不再要求调用工具，循环结束。就这么简单。
所谓"Agent 会自己想办法"，本质是它在多轮里反复观察工具结果。

一个容易踩的坑：必须设步数上限。模型可能陷进"读文件→改文件→再读"的
死循环里烧你的 token，没上限就停不下来。
"""

from .bus import Bus
from .provider import OpenAICompatProvider, ProviderError
from .session import Session
from .tools import ToolRegistry


def run_turn(
    session: Session,
    provider: OpenAICompatProvider,
    registry: ToolRegistry,
    user_text: str,
    bus: Bus,
    max_steps: int,
) -> str:
    """处理用户的一条消息，返回最终的助手回复。"""
    session.add({"role": "user", "content": user_text})
    bus.publish("turn_start", text=user_text)

    for step in range(1, max_steps + 1):
        bus.publish("llm_request", step=step)
        try:
            message = provider.chat(session.messages, registry.schemas())
        except ProviderError as exc:
            bus.publish("error", message=str(exc))
            return f"（模型调用失败：{exc}）"

        # 规整成可以回传的格式：OpenAI 要求 content 字段存在，不能是 None
        assistant = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            assistant["tool_calls"] = message["tool_calls"]
        session.add(assistant)

        calls = assistant.get("tool_calls") or []
        if not calls:
            bus.publish("turn_end", content=assistant["content"])
            return assistant["content"]

        # 模型可能一次要求调用多个工具。这里顺序执行，
        # ORG2 有并行批次处理（tool_execution/），我们先不引入复杂度。
        for call in calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or "{}"
            bus.publish("tool_start", name=name, args=args)

            output = registry.execute(name, args)

            bus.publish("tool_end", name=name, output=output)
            session.record_event(
                "tool_call", {"name": name, "args": args, "output": output[:2000]}
            )
            session.add(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,
                    "content": output,
                }
            )

    bus.publish("turn_end", content="")
    return f"（已执行 {max_steps} 步仍未完成，本轮中止。可以让我接着做。）"
