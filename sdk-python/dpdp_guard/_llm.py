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


def make_client():
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None
