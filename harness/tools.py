"""工具层。

对应 ORG2 里的 `agent_core::core::tools`（trait 在 `tools/traits.rs`）。

这里是整个 harness 最关键的抽象。模型本身不能读文件、不能跑命令，
它只会输出一段 JSON 说"我想调用 read_file，参数是这些"。
真正干活的是这里注册的函数。

一个工具 = 名字 + 说明 + 参数 schema + 一个普通 Python 函数。
模型看到的是前三项（写进请求的 tools 字段），第四项只有你能看到。
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config


# ---------------------------------------------------------------------------
# 抽象：Tool 与注册表
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict], str]

    def schema(self) -> dict:
        """转换成 OpenAI 的 function calling 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, raw_args: str) -> str:
        """执行一个工具调用。

        关键设计：无论工具内部怎么炸，这里都必须返回**字符串**。
        因为工具结果是塞回消息历史喂给模型的，绝不能抛异常打断循环 ——
        模型要看得到"失败原因"才能自己纠正。
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：没有名为 {name} 的工具。可用工具：{', '.join(self._tools)}"

        import json

        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            return f"错误：参数不是合法 JSON：{raw_args[:200]}"

        try:
            return tool.run(args)
        except Exception as exc:  # noqa: BLE001 —— 见上，故意兜住全部异常
            return f"错误：{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# 安全：路径沙箱
# ---------------------------------------------------------------------------


def _sandbox(path_str: str) -> Path:
    """把所有路径解析到工作目录内，越界直接拒绝。

    对应 ORG2 的 `foundation::security`。这是必须的 ——
    模型可能被你的一句提示词骗着去读 `C:\\Users\\你\\密码.txt`。
    不做这层限制，你的 harness 就是一个提权后门。
    """
    root = config.ROOT.resolve()
    target = (root / path_str).resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"路径越界，只允许访问 {root} 内部：{path_str}")
    return target


def _truncate(text: str, limit: int = config.MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(已截断，原长 {len(text)} 字符)"


# ---------------------------------------------------------------------------
# 四个内置工具
# ---------------------------------------------------------------------------


def _read_file(args: dict) -> str:
    path = _sandbox(args["path"])
    if not path.exists():
        return f"错误：文件不存在 {args['path']}"
    if path.is_dir():
        return f"错误：{args['path']} 是目录，请用 list_dir"

    offset = int(args.get("offset", 1))
    limit = int(args.get("limit", 200))
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    slice_ = lines[offset - 1 : offset - 1 + limit]
    body = "\n".join(f"{offset + i:>5}│{line}" for i, line in enumerate(slice_))
    if not slice_:
        return f"（{args['path']} 共 {len(lines)} 行，offset 超出范围）"
    tail = "" if offset - 1 + limit >= len(lines) else f"\n...(共 {len(lines)} 行)"
    return _truncate(body + tail)


def _write_file(args: dict) -> str:
    path = _sandbox(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    content = args["content"]
    path.write_text(content, encoding="utf-8")
    return f"已写入 {args['path']}（{len(content)} 字符）"


def _list_dir(args: dict) -> str:
    path = _sandbox(args.get("path", "."))
    if not path.exists():
        return f"错误：目录不存在 {args.get('path', '.')}"
    if not path.is_dir():
        return f"错误：{args.get('path')} 不是目录"
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    lines = []
    for entry in entries[:200]:
        if entry.name in {"__pycache__", ".git", "node_modules", "sessions"}:
            continue
        lines.append(("[dir]  " if entry.is_dir() else "       ") + entry.name)
    return _truncate("\n".join(lines) or "（空目录）")


def _run_shell(args: dict) -> str:
    """执行命令。对应 ORG2 的终端工具。

    注意 cwd 锁定在工作目录，且带超时 —— 一个死循环命令不该把 Agent 卡死。
    真实产品里这里还要做命令白名单/审批，见 ORG2 的 ResolvedToolPolicy。
    """
    command = args["command"]
    timeout = int(args.get("timeout", config.SHELL_TIMEOUT))
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"错误：命令超时（{timeout}s）被终止：{command}"

    parts = []
    if proc.stdout.strip():
        parts.append(proc.stdout.rstrip())
    if proc.stderr.strip():
        parts.append("[stderr]\n" + proc.stderr.rstrip())
    parts.append(f"[exit {proc.returncode}]")
    return _truncate("\n".join(parts))


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="read_file",
            description="读取文本文件的内容，返回带行号的文本。改动文件前应当先读。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的文件路径"},
                    "offset": {"type": "integer", "description": "起始行号，从 1 开始，默认 1"},
                    "limit": {"type": "integer", "description": "最多读多少行，默认 200"},
                },
                "required": ["path"],
            },
            run=_read_file,
        )
    )

    registry.register(
        Tool(
            name="write_file",
            description="把内容完整写入文件（覆盖）。父目录不存在会自动创建。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的文件路径"},
                    "content": {"type": "string", "description": "要写入的完整内容"},
                },
                "required": ["path", "content"],
            },
            run=_write_file,
        )
    )

    registry.register(
        Tool(
            name="list_dir",
            description="列出一个目录下的文件和子目录。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作目录的目录路径，默认当前目录"},
                },
            },
            run=_list_dir,
        )
    )

    registry.register(
        Tool(
            name="run_shell",
            description="在工作目录中执行一条 shell 命令，返回 stdout、stderr 和退出码。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 60"},
                },
                "required": ["command"],
            },
            run=_run_shell,
        )
    )

    return registry
