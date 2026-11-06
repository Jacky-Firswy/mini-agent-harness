"""冒烟测试：不需要 API Key 就能验证核心逻辑。

运行：python tests/smoke_test.py

这里故意不用 pytest —— 少一个安装步骤。
等你项目变大了、需要 fixture 和参数化时，再换 pytest 才划算。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from harness import config  # noqa: E402
from harness.session import Session  # noqa: E402
from harness.tools import build_registry  # noqa: E402

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}  {detail}")


def test_registry() -> None:
    print("工具注册表")
    registry = build_registry()
    schemas = registry.schemas()
    check("注册了 4 个工具", len(schemas) == 4, f"实际 {len(schemas)}")
    check(
        "schema 是 function 格式",
        all(s["type"] == "function" and "name" in s["function"] for s in schemas),
    )
    check(
        "调用不存在的工具不抛异常",
        "没有名为" in registry.execute("nope", "{}"),
    )
    check(
        "参数不是合法 JSON 时返回错误字符串",
        "不是合法 JSON" in registry.execute("read_file", "{{{oops"),
    )


def test_tools() -> None:
    print("\n工具执行")
    registry = build_registry()
    config.SESSION_DIR.mkdir(exist_ok=True)

    out = registry.execute(
        "write_file",
        '{"path": "sessions/_smoke_test.txt", "content": "hello\\nworld"}',
    )
    check("write_file 成功", "已写入" in out, out)

    out = registry.execute("read_file", '{"path": "sessions/_smoke_test.txt"}')
    check("read_file 带回行号", "hello" in out and "│" in out, out)

    out = registry.execute("list_dir", "{}")
    check("list_dir 能列出目录", "harness" in out, out[:120])

    out = registry.execute("run_shell", '{"command": "echo harness-ok"}')
    check("run_shell 有输出和退出码", "harness-ok" in out and "exit 0" in out, out)

    out = registry.execute("read_file", '{"path": "no_such_file_xyz.txt"}')
    check("读不存在的文件返回错误而非崩溃", "不存在" in out, out)

    (config.ROOT / "sessions" / "_smoke_test.txt").unlink(missing_ok=True)


def test_sandbox() -> None:
    print("\n路径沙箱")
    registry = build_registry()
    out = registry.execute("read_file", '{"path": "../../../Windows/win.ini"}')
    check("越界路径被拒绝", "越界" in out, out)
    out = registry.execute("write_file", '{"path": "../escape.txt", "content": "x"}')
    check("越界写入被拒绝", "越界" in out, out)


def test_session() -> None:
    print("\n会话持久化")
    session = Session.create()
    session.add({"role": "user", "content": "你好"})
    session.add({"role": "assistant", "content": "在的"})
    check("消息进了内存", len(session.messages) == 2)
    check("日志文件已生成", session.log_path.exists())

    loaded = Session.load(session.id)
    check("重新加载能还原消息", len(loaded.messages) == 2)
    check("内容一致", loaded.messages[0]["content"] == "你好")
    check("会话出现在列表里", session.id in Session.list_sessions())

    session.log_path.unlink(missing_ok=True)


class FakeProvider:
    """假模型：不需要网络和 API Key，用来验证循环本身。

    剧本是固定好的：第一次请求要求调用 run_shell，第二次给出最终回答。
    真实模型无非是把这个剧本换成了它自己想的。
    """

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "echo loop-works"}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "命令执行完了，输出是 loop-works。"}


def test_loop() -> None:
    print("\n回合循环（用假模型）")
    from harness.bus import Bus
    from harness.loop import run_turn

    registry = build_registry()
    bus = Bus()
    events = []
    bus.subscribe(lambda name, data: events.append(name))

    session = Session.create()
    provider = FakeProvider()
    answer = run_turn(session, provider, registry, "跑个 echo 看看", bus, max_steps=5)

    check("模型被调用了 2 次", provider.calls == 2, f"实际 {provider.calls}")
    check("返回了最终回答", "loop-works" in answer, answer)
    check(
        "消息顺序正确：user → assistant → tool → assistant",
        [m["role"] for m in session.messages]
        == ["user", "assistant", "tool", "assistant"],
        str([m["role"] for m in session.messages]),
    )
    check("工具真的执行了", "loop-works" in session.messages[2]["content"])
    check("事件总线发出了 tool_start", "tool_start" in events, str(events))
    check("事件总线发出了 turn_end", "turn_end" in events, str(events))

    session.log_path.unlink(missing_ok=True)


def test_loop_guard() -> None:
    print("\n循环上限保护")
    from harness.bus import Bus
    from harness.loop import run_turn

    class AlwaysToolProvider:
        def chat(self, messages, tools):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_x",
                        "type": "function",
                        "function": {"name": "list_dir", "arguments": "{}"},
                    }
                ],
            }

    session = Session.create()
    answer = run_turn(
        session, AlwaysToolProvider(), build_registry(), "停不下来", Bus(), max_steps=3
    )
    check("达到上限会中止", "中止" in answer, answer)
    session.log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print(f"工作目录 {config.ROOT}\n")
    test_registry()
    test_tools()
    test_sandbox()
    test_session()
    test_loop()
    test_loop_guard()
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)
