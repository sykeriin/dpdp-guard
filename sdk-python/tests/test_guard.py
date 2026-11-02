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
