"""命令行入口。

对应 ORG2 里的 `agent_core::state::commands` —— 但它只服务自己的终端。
ORG2 那一层是 Tauri 命令，供前端的 React 界面调用；这里换成 print。

想换界面（网页、桌面）只要换这一个文件，下面四层一行都不用动。
这就是分层的好处。
"""

import argparse
import sys

from . import config
from .bus import Bus
from .loop import run_turn
from .provider import ProviderError, build_provider
from .session import Session, replay
from .tools import build_registry


# Windows 终端默认是 GBK，输出中文和特殊符号会乱码/报错，这里强制改成 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def make_printer():
    """订阅总线，把事件打印到终端。"""

    def handler(event: str, data: dict) -> None:
        if event == "tool_start":
            print(f"\n  ⚙ {data['name']}  {_short(data['args'], 100)}")
        elif event == "tool_end":
            first = (data["output"] or "").splitlines()
            head = first[0] if first else ""
            print(f"    ↳ {_short(head, 120)}")
        elif event == "error":
            print(f"\n  ✗ {data['message']}")
        elif event == "llm_request" and data.get("step", 1) > 1:
            print(f"  … 第 {data['step']} 轮思考")

    return handler


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def cmd_check() -> int:
    print("环境自检")
    print(f"  工作目录   {config.ROOT}")
    print(f"  会话目录   {config.SESSION_DIR}")
    print(f"  API 地址   {config.BASE_URL}")
    print(f"  模型       {config.MODEL}")
    print(f"  API Key    {'已配置' if config.API_KEY else '缺失 —— 需要创建 .env'}")
    registry = build_registry()
    names = [t.name for t in registry._tools.values()]
    print(f"  已注册工具 {', '.join(names)}")
    return 0 if config.API_KEY else 1


def cmd_tools() -> int:
    for tool in build_registry()._tools.values():
        print(f"{tool.name}")
        print(f"  {tool.description}")
        required = tool.parameters.get("required", [])
        print(f"  必填参数: {', '.join(required) or '无'}\n")
    return 0


def cmd_sessions() -> int:
    sessions = Session.list_sessions()
    if not sessions:
        print("还没有任何会话记录。")
        return 0
    for sid in sessions:
        print(sid)
    return 0


def cmd_chat(once: str | None) -> int:
    try:
        provider = build_provider()
    except ProviderError as exc:
        print(f"✗ {exc}")
        return 1

    registry = build_registry()
    bus = Bus()
    bus.subscribe(make_printer())
    session = Session.create()

    print(f"会话 {session.id}")
    print(f"模型 {config.MODEL} @ {config.BASE_URL}")
    print("输入问题开始，exit 退出。\n")

    while True:
        if once is not None:
            text = once
        else:
            try:
                text = input("你 › ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit", ":q"}:
                break

        answer = run_turn(session, provider, registry, text, bus, config.MAX_STEPS)
        if answer:
            print(f"\n助手 › {answer}\n")

        if once is not None:
            break

    print(f"记录已保存：sessions/{session.id}.jsonl")
    print(f"回放这次对话：python -m harness.main --replay {session.id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="harness", description="一个最小可用的本地编程 Agent"
    )
    parser.add_argument("--once", metavar="提问", help="只问一次就退出")
    parser.add_argument("--replay", metavar="会话ID", help="回放一次会话")
    parser.add_argument("--sessions", action="store_true", help="列出所有会话")
    parser.add_argument("--tools", action="store_true", help="列出所有工具")
    parser.add_argument("--check", action="store_true", help="检查环境配置")
    args = parser.parse_args()

    if args.check:
        return cmd_check()
    if args.tools:
        return cmd_tools()
    if args.sessions:
        return cmd_sessions()
    if args.replay:
        replay(args.replay)
        return 0
    return cmd_chat(args.once)


if __name__ == "__main__":
    sys.exit(main())
