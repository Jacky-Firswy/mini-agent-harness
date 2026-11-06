"""事件总线。

对应 ORG2 里的 `agent_core::foundation::bus`。

为什么需要它：引擎不该知道界面长什么样。引擎只管 publish("tool_start", ...)，
谁来订阅、怎么显示，是上层的事。这样同一套引擎同时喂给终端、喂给 Web UI、
喂给轨迹录制器，都不用改一行引擎代码。
"""

from typing import Any, Callable

Handler = Callable[[str, dict], None]


class Bus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def publish(self, event: str, **data: Any) -> None:
        for handler in self._handlers:
            handler(event, data)
