"""会话层。

对应 ORG2 里的 `agent_core::core::session` + `foundation::persistence`。

一次对话 = 一串消息。但消息只在内存里，进程一关就没了 ——
ORG2 的核心卖点"会话可回放"靠的就是把每一步都落盘。

这里用最朴素的方案：JSONL，一行一个事件，只追加不修改。
好处是崩溃时前面写好的不会坏，坏处是不方便查询 —— 所以 ORG2 用 SQLite。
先用 JSONL 把概念跑通，等你需要按时间/按文件检索时再换 SQLite 就很自然了。
"""

import json
import time
import uuid
from pathlib import Path

from . import config


class Session:
    def __init__(self, session_id: str, log_path: Path) -> None:
        self.id = session_id
        self.log_path = log_path
        self.messages: list[dict] = []

    # --- 创建与加载 ---------------------------------------------------------

    @classmethod
    def create(cls) -> "Session":
        config.SESSION_DIR.mkdir(exist_ok=True)
        session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        return cls(session_id, config.SESSION_DIR / f"{session_id}.jsonl")

    @classmethod
    def load(cls, session_id: str) -> "Session":
        log_path = config.SESSION_DIR / f"{session_id}.jsonl"
        if not log_path.exists():
            raise FileNotFoundError(f"找不到会话 {session_id}")
        session = cls(session_id, log_path)
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") == "message":
                session.messages.append(event["payload"])
        return session

    @classmethod
    def list_sessions(cls) -> list[str]:
        if not config.SESSION_DIR.exists():
            return []
        return sorted((p.stem for p in config.SESSION_DIR.glob("*.jsonl")), reverse=True)

    # --- 记录 ---------------------------------------------------------------

    def _record(self, event_type: str, payload: dict) -> None:
        line = json.dumps(
            {"ts": time.time(), "type": event_type, "payload": payload},
            ensure_ascii=False,
        )
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def add(self, message: dict) -> None:
        """加一条消息：进内存，同时落盘。两件事永远一起做。"""
        self.messages.append(message)
        self._record("message", message)

    def record_event(self, event: str, data: dict) -> None:
        """记录非消息类事件（工具进度、错误等），仅供回放查看。"""
        self._record("event", {"event": event, **data})


def replay(session_id: str) -> None:
    """把一次会话完整播出来，像看录像。"""
    log_path = config.SESSION_DIR / f"{session_id}.jsonl"
    if not log_path.exists():
        print(f"找不到会话 {session_id}")
        return

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        when = time.strftime("%H:%M:%S", time.localtime(event["ts"]))

        if event["type"] != "message":
            payload = event["payload"]
            print(f"  [{when}] · {payload.get('event')}")
            continue

        msg = event["payload"]
        role = msg.get("role")
        content = msg.get("content") or ""

        if role == "user":
            print(f"\n[{when}] 你 › {content}")
        elif role == "assistant":
            if content:
                print(f"[{when}] 助手 › {content}")
            for call in msg.get("tool_calls") or []:
                fn = call["function"]
                print(f"[{when}] 调用 › {fn['name']}({fn['arguments'][:120]})")
        elif role == "tool":
            head = content.splitlines()[0] if content else ""
            print(f"          结果 ‹ {head[:160]}")
