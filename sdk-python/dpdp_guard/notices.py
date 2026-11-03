from functools import lru_cache
from importlib import resources
import yaml


@lru_cache(maxsize=4)
def load(path: str | None = None) -> dict:
    if path:
        return yaml.safe_load(open(path, encoding="utf-8"))
    return yaml.safe_load(resources.files("dpdp_guard").joinpath("notices/notice_v1.yaml").read_text(encoding="utf-8"))


def lang_of(text: str, default: str = "en") -> str:
    return "hi" if any("ऀ" <= c <= "ॿ" for c in text) else default


def render(name: str, lang: str = "en", cfg: dict | None = None, **kw) -> str:
    cfg = cfg or load()
    t = cfg["templates"][name]
    s = t.get(lang) or t["en"]
    return s.format(**kw).strip()


def purpose_lines(purposes: list[str], lang: str = "en", cfg: dict | None = None) -> str:
    cfg = cfg or load()
    return "\n".join(f"{i}. {cfg['purposes'][p].get(lang) or cfg['purposes'][p]['en']}" for i, p in enumerate(purposes, 1))


def notice(purposes: list[str], business: str, privacy_url: str, lang: str = "en", cfg: dict | None = None) -> str:
    cfg = cfg or load()
    lines = "\n".join(f"{i}. {cfg['purposes'][p].get(lang) or cfg['purposes'][p]['en']}" for i, p in enumerate(purposes, 1))
    return render("notice", lang, cfg, business=business, purpose_lines=lines, privacy_url=privacy_url)
