"""配置层。

对应 ORG2 里的 `agent_core::foundation` —— 所有模块都能读它，它不依赖任何上层。
原则：配置从环境变量来，写死在代码里的只有默认值。
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = ROOT / "sessions"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """极简 .env 解析器，够用就行，不引第三方库。

    存在的意义：API Key 不该出现在代码里，也不该出现在命令行历史里。
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 已存在的环境变量优先，方便临时覆盖
        os.environ.setdefault(key, value)


load_dotenv()

# --- 模型接入 ---------------------------------------------------------------
# 任何 OpenAI 兼容接口都能用：DeepSeek / OpenAI / Moonshot / 智谱 / Ollama
API_KEY = os.environ.get("HARNESS_API_KEY", "")
BASE_URL = os.environ.get("HARNESS_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("HARNESS_MODEL", "deepseek-chat")

# --- 运行限制 ---------------------------------------------------------------
MAX_STEPS = int(os.environ.get("HARNESS_MAX_STEPS", "25"))
SHELL_TIMEOUT = int(os.environ.get("HARNESS_SHELL_TIMEOUT", "60"))
MAX_OUTPUT_CHARS = 8000

# --- 系统提示 ---------------------------------------------------------------
SYSTEM_PROMPT = f"""你是一个运行在本地终端里的编程 Agent。

当前工作目录：{ROOT}

你可以调用工具来读写文件和执行命令。工作方式是：
1. 先想清楚要做什么
2. 需要信息就调用工具去拿，不要凭空猜测文件内容
3. 每次工具调用只做一件事，结果会返回给你
4. 确认完成后再结束回答

规则：
- 修改文件前先读一遍，不要盲改
- 命令输出可能被截断，必要时缩小范围重试
- 回答用中文，简洁，不要复述工具输出
- 做不到的事情直接说做不到
"""
