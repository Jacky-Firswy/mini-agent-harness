"""一个最小可用的编程 Agent harness。

分层（依赖只能向下）：

    main.py      命令行入口        ← 对应 ORG2 的 state/
    loop.py      回合循环          ← 对应 core/turn_executor
    tools.py     工具与注册表      ← 对应 core/tools
    provider.py  模型接入          ← 对应 core/providers
    session.py   会话与落盘        ← 对应 core/session
    bus.py       事件总线          ← 对应 foundation/bus
    config.py    配置              ← 对应 foundation/
"""

__version__ = "0.1.0"
