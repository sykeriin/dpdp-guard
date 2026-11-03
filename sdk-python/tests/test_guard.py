import pytest
from dpdp_guard import Guard, LocalStore

@pytest.fixture
def g():
    return Guard("t1", "Acme Store", ["order_updates"], ["marketing"], store=LocalStore())

def test_first_message_gets_notice_not_agent(g):
    r = g("hi, my number is 9876543210", "u1", "whatsapp")
    assert r.action == "reply" and "order_updates" not in r.reply_text and "Marketing" in r.reply_text
    assert g.store.pii("t1") == []          # nothing stored before consent

def test_per_purpose_consent_and_forward(g):
    g("hi", "u1")
    r = g("1", "u1")
    assert r.granted == ["order_updates"]
    r = g("my phone is 9876543210", "u1")
    assert r.action == "forward" and "9876543210" not in r.masked_message and "9876543210" in r.message
    st = g.store.consent_state("t1", g._pid("u1"))
    assert st == {"order_updates": True, "marketing": False}   # marketing separate, not bundled
    assert g.store.pii("t1")[0]["purpose"] == "order_updates"

def test_bare_yes_is_not_specific_consent(g):
    g("hi", "u1")
    r = g("yes", "u1")
    assert r.action == "reply" and g.store.consent_state("t1", g._pid("u1")) == {}

def test_decline_blocks(g):
    g("hi", "u1"); g("none", "u1")
    assert g("order status?", "u1").action == "block"

def test_hindi_notice_and_consent():
    g = Guard("t1", "Acme", ["order_updates"], store=LocalStore())
    r = g("नमस्ते", "u1")
    assert "सहमति" in r.reply_text or "आपका" in r.reply_text
    assert g("1", "u1").granted == ["order_updates"]

def test_rights_before_consent_and_erasure_logged(g):
    r = g("meri details hatao", "u2")
    assert r.intent == "erasure" and r.rights_ref
    assert g.store.rights("t1")[0]["kind"] == "erasure"

def test_withdraw_flips_consent(g):
    g("hi", "u1"); g("1 2", "u1")
    g("I withdraw my consent", "u1")
    assert not any(g.store.consent_state("t1", g._pid("u1")).values())

def test_minor_blocked(g):
    r = g("I am 14 years old", "kid")
    assert r.action == "block" and "18" in r.reply_text

def test_ledger_chain_and_tamper(g):
    g("hi", "u1"); g("1", "u1"); g("call 9876543210", "u1")
    ok, _ = g.store.verify("t1"); assert ok
    with pytest.raises(Exception):
        g.store.db.execute("update events set hash='x' where seq=1")      # trigger blocks
    # forge by bypassing trigger
    g.store.db.execute("drop trigger events_no_update")
    g.store.db.execute("update events set event=replace(event,'notice_shown','nothing') where seq=1")
    ok, bad = g.store.verify("t1")
    assert not ok and bad == 0

def test_erasure_request_also_stops_processing(g):
    g("hi", "u1"); g("1", "u1")
    assert g("hello", "u1").action == "forward"
    g("delete my data", "u1")
    assert g("where is my order", "u1").action == "block"      # no further processing after erasure request
    # and consent history is retained as evidence
    assert [c["granted"] for c in g.store.consents("t1") if c["purpose"] == "order_updates"] == [1, 0]

def test_transcripts_are_masked_and_erasable(g):
    g("hi", "u1"); g("1", "u1"); g("call 9876543210", "u1")
    rows = g.store.db.execute("select text from transcripts").fetchall()
    assert rows and not any("9876543210" in r["text"] for r in rows)
    assert g.store.erase_principal("t1", g._pid("u1")) == len(rows)


def test_fail_closed_when_store_down():
    import httpx
    from dpdp_guard import HttpStore
    dead = HttpStore("http://127.0.0.1:1", "k", timeout=0.5)
    r = Guard("t", "Acme", ["order_updates"], store=dead)("call 9876543210", "u")
    assert r.action == "block" and r.error and "9876543210" not in r.masked_message and r.message == ""


def test_fail_open_is_explicit_opt_in():
    from dpdp_guard import HttpStore
    dead = HttpStore("http://127.0.0.1:1", "k", timeout=0.5)
    r = Guard("t", "Acme", ["order_updates"], store=dead, fail_mode="open")("hello", "u")
    assert r.action == "forward" and r.error


# ---- guardian / parental consent (Rules 10-12). Consent is self-asserted: no identity verification.
def _minor_flow(g):
    r1 = g("I am 14 years old, I want to order", "kid")
    assert r1.action == "block" and "mobile number" in r1.reply_text
    r2 = g("my mom's number is 98765 11111", "kid")
    return r1, r2

def test_guardian_flow_end_to_end(g):
    _, r2 = _minor_flow(g)
    assert r2.action == "block" and len(r2.notify) == 1
    assert r2.notify[0]["to"] == "9876511111" and "parent/guardian" in r2.notify[0]["text"] and "1." in r2.notify[0]["text"]
    assert g("hello again", "kid").action == "block"                      # still waiting; agent sees nothing
    assert g.store.consent_state("t1", g.pid("kid")) == {}                # no consent from the child itself
    ans = g("1", "919876511111")                                          # guardian replies from +91 form of the same number
    assert ans.action == "reply" and "recorded" in ans.reply_text.lower()
    st = g.store.consent_state("t1", g.pid("kid"))
    assert st == {"order_updates": True, "marketing": False}              # recorded against the child, per purpose
    r = g("my pin is 560001", "kid")
    assert r.action == "forward" and "560001" not in r.masked_message
    ev = [e["event"] for e in g.store.events("t1")]
    assert any(e["type"] == "parental_consent_granted" and e["payload"]["verification"] == "self-asserted-number" for e in ev)
    assert "9876511111" not in str(ev) and "98765" not in str(ev)         # raw guardian number never reaches the ledger

def test_guardian_declines(g):
    _minor_flow(g)
    g("none", "9876511111")
    r = g("can I order now", "kid")
    assert r.action == "block" and "did not give consent" in r.reply_text
    assert g.store.consent_state("t1", g.pid("kid")).get("order_updates") is False

def test_guardian_cannot_be_the_child_and_needs_a_number(g):
    g("I am 15", "9000000001")
    assert "mobile number" in g("no idea", "9000000001").reply_text
    assert "can't be your own" in g("my number is 90000 00001", "9000000001").reply_text

def test_unclear_guardian_reply_reasks_without_consent(g):
    _minor_flow(g)
    r = g("yes", "9876511111")                                            # bare yes to a multi-purpose notice is not specific consent
    assert r.action == "reply" and "1." in r.reply_text
    assert g.store.consent_state("t1", g.pid("kid")) == {}

def test_phone_id_normalisation():
    gd = Guard("t", "A", ["x"], store=LocalStore())
    assert gd.pid("+91 98765 43210") == gd.pid("919876543210") == gd.pid("9876543210") != gd.pid("9876543211")
