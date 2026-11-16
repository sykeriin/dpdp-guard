"""Shared Anthropic call helper for the optional LLM passes (intent fallback, name/address extraction).

Why this exists: claude-haiku-5-5 thinks by default, so a response can START with a `thinking` block (empty text unless
display is requested). Reading `content[0].text` then fails or truncates. For these tiny classification calls we turn thinking
off (allowed at effort <= high; effort here is low) and read the first *text* block, never content[0]."""

DEFAULT_MODEL = "claude-haiku-5-5"


def call_text(client, system: str, user: str, max_tokens: int = 16, model: str = DEFAULT_MODEL) -> str | None:
    """Returns the model's text, or None on refusal / truncation / no text block. Exceptions propagate to the caller."""
    r = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        thinking={"type": "disabled"}, output_config={"effort": "low"},
        messages=[{"role": "user", "content": user}],
    )
    if getattr(r, "stop_reason", None) in ("refusal", "max_tokens"):
        return None
    return next((b.text for b in r.content if getattr(b, "type", "text") == "text"), None)


class LocalClient:
    """Duck-types the slice of anthropic.Anthropic that call_text uses (`messages.create`), backed by any OpenAI-compatible
    chat endpoint (Ollama, LM Studio, llama.cpp server, vLLM). Anthropic-only kwargs (thinking, output_config) are dropped and
    the caller's Claude model name is replaced by `model`. Same fail-safe contract: errors propagate and callers return None."""

    def __init__(self, base_url: str, model: str, api_key: str = "local", timeout: float = 60.0):
        import httpx
        self.base_url, self.model, self.messages = base_url.rstrip("/"), model, self
        self._http = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    def create(self, *, system: str, messages: list, max_tokens: int = 16, **_ignored):
        r = self._http.post(f"{self.base_url}/chat/completions", json={
            "model": self.model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": system}, *messages]})
        r.raise_for_status()
        ch = r.json()["choices"][0]
        u = r.json().get("usage") or {}
        from types import SimpleNamespace as NS
        return NS(content=[NS(type="text", text=ch["message"].get("content") or "")],
                  stop_reason="max_tokens" if ch.get("finish_reason") == "length" else "end_turn",
                  usage=NS(input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0)))


def make_client():
    """DPDP_LLM_BASE_URL (+ DPDP_LLM_MODEL) selects a local/OpenAI-compatible model, e.g. http://localhost:11434/v1 for Ollama.
    Otherwise Anthropic if the SDK and a key are available; otherwise None (LLM passes are skipped)."""
    import os
    base = os.environ.get("DPDP_LLM_BASE_URL")
    if base:
        try:
            return LocalClient(base, os.environ.get("DPDP_LLM_MODEL", "qwen2.5:3b"), os.environ.get("DPDP_LLM_API_KEY", "local"))
        except Exception:
            return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None
