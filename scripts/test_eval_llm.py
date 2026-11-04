import importlib.util, pathlib, subprocess, sys, os
spec = importlib.util.spec_from_file_location("ev", pathlib.Path(__file__).parent / "eval_llm_intent.py")
ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)

class B:
    def __init__(self, type, text=None):
        self.type = type
        if text is not None: self.text = text
class U:  input_tokens, output_tokens = 120, 2
class Fake:
    """answers 'erasure' for anything containing 'purge', else 'none'"""
    @property
    def messages(self): return self
    def create(self, **kw):
        class R: pass
        r = R(); r.stop_reason = "end_turn"; r.usage = U()
        r.content = [B("text", "erasure" if "purge" in kw["messages"][0]["content"] else "none")]; return r

ROWS = [("erasure", "delete my data"), ("erasure", "could you purge what you hold"), ("stop", "take me off your marketing list"), (None, "where is my order")]

def test_evaluate_counts_llm_rescues_and_cost():
    r = ev.evaluate(ROWS, Fake())
    assert r["rules_only"]["silent_misses"] == 2 and r["rules_only"]["accuracy"] == 0.5
    assert r["rules_plus_llm"]["silent_misses"] == 1 and r["rules_plus_llm"]["accuracy"] == 0.75      # 'purge' rescued, 'take me off' not
    assert r["llm_calls"] == 3        # every message the rules return None for, INCLUDING the benign 'where is my order'; 'delete my data' never hits the model
    assert r["input_tokens"] == 360 and abs(r["cost_usd"] - (360 * 0.10 / 1e6 + 6 * 0.50 / 1e6)) < 1e-9

def test_llm_false_positive_is_counted():
    class Eager(Fake):
        def create(self, **kw):
            r = super().create(**kw); r.content = [B("text", "erasure")]; return r
    r = ev.evaluate([(None, "tell me about the offers")], Eager())
    assert r["rules_plus_llm"]["false_positives"] == 1

def test_refuses_without_credentials_and_exits_2():
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    p = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / "eval_llm_intent.py")], env=env, capture_output=True, text=True)
    assert p.returncode == 2 and "never fabricates" in p.stderr and p.stdout == ""
