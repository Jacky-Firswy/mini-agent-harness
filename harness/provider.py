"""模型接入层。

对应 ORG2 里的 `agent_core::core::providers`。

我们只实现一种驱动：OpenAI Chat Completions 兼容格式。
DeepSeek、OpenAI、Moonshot、智谱、本地 Ollama 全都说这套协议，
所以一个实现打通一大片 —— 这也是 ORG2 里 `openai_compat` 驱动存在的理由。

用标准库 urllib 而不是 requests：少一个安装步骤，初学者打开就能跑。
"""

import json
import time
import urllib.error
import urllib.request

from . import config


class ProviderError(Exception):
    """模型调用失败。单独分类，方便上层决定要不要重试。"""


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """发一轮对话，返回 assistant 消息。

        注意这里是一次性返回，不是流式。流式要在 SSE 里拼 tool_calls 增量，
        代码会多出一倍 —— 先用简单版本把循环跑通，之后再升级。
        """
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools

        for attempt in range(3):
            try:
                return self._post(payload)
            except ProviderError as exc:
                if attempt == 2:
                    raise
                wait = 2**attempt
                print(f"  [重试 {attempt + 1}/2] {exc}，{wait}s 后再试")
                time.sleep(wait)
        raise ProviderError("不可达")  # 逻辑上到不了，让类型检查安心

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"网络错误: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"响应不是合法 JSON: {exc}") from exc

        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"响应结构异常: {json.dumps(data)[:500]}") from exc


def build_provider() -> OpenAICompatProvider:
    if not config.API_KEY:
        raise ProviderError(
            "没有找到 API Key。\n"
            "做法：把 .env.example 复制成 .env，填上 HARNESS_API_KEY。"
        )
    return OpenAICompatProvider(
        base_url=config.BASE_URL,
        api_key=config.API_KEY,
        model=config.MODEL,
    )
