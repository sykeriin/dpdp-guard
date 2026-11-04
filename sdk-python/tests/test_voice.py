import pytest
from dpdp_guard import Guard, LocalStore, VoiceGuard
from dpdp_guard.voice import parse_answer

@pytest.fixture
def v():
    g = Guard("t1", "Acme Clinic", ["order_updates"], ["marketing"], store=LocalStore())
    return VoiceGuard(g), g

def test_parse_answer():
    assert parse_answer(digits="1") is True and parse_answer(digits="2") is False
    assert parse_answer("yes please") is True and parse_answer("haan ji") is True and parse_answer("nahi chahiye") is False
    assert parse_answer("हाँ") is True and parse_answer("नहीं") is False
    assert parse_answer("yes no maybe") is None and parse_answer("what?") is None and parse_answer("") is None
    assert parse_answer("no", digits="1") is True                      # keypad beats speech

def test_full_call_flow_per_purpose_consent_then_forward(v):
    vg, g = v; pid = g.pid("919876543210")
    r = vg.handle("919876543210", speech="hello")
    assert r.action == "say" and "Acme Clinic" in r.say and "Order updates" in r.say and "Marketing" not in r.say    # ONE purpose at a time
    assert g.store.consent_state("t1", pid) == {}                                                                    # nothing recorded yet
    r = vg.handle("919876543210", digits="1")
    assert "Marketing" in r.say and g.store.consent_state("t1", pid) == {}                                           # still nothing until all answered
    r = vg.handle("919876543210", speech="no thanks")
    assert r.action == "say" and "saved" in r.say
    assert g.store.consent_state("t1", pid) == {"order_updates": True, "marketing": False}                           # specific, not bundled
    r = vg.handle("919876543210", speech="my number is 9876543210 and I need an appointment")
    assert r.action == "forward" and "9876543210" in r.agent_text and "9876543210" not in r.masked_text
    ev = [e["event"] for e in g.store.events("t1")]
    by = {e["payload"]["purpose"]: e["payload"]["channel"] for e in ev if e["type"].startswith("consent_")}
    assert by == {"order_updates": "voice-dtmf", "marketing": "voice-speech"}          # each answer keeps its OWN method
    assert ev[0]["type"] == "voice_notice_played"
    assert {e["payload"]["channel"] for e in ev if e["type"].startswith("consent_")} == {"voice-dtmf", "voice-speech"}  # evidence records HOW consent was given

def test_unclear_answer_repeats_and_records_nothing(v):
    vg, g = v
    vg.handle("u", speech="hi")
    r = vg.handle("u", speech="umm what is this")
    assert r.action == "say" and "didn't catch" in r.say and "Order updates" in r.say
    assert g.store.consent_state("t1", g.pid("u")) == {}

def test_required_declined_ends_call_and_blocks_next_time(v):
    vg, g = v
    vg.handle("u", speech="hi"); vg.handle("u", digits="2")
    r = vg.handle("u", digits="2")
    assert r.action == "end" and "will not process" in r.say
    assert vg.handle("u", speech="I want to book").action == "end"          # later call: still no agent access

def test_rights_request_honoured_mid_consent_menu(v):
    vg, g = v
    vg.handle("u", speech="hi")
    r = vg.handle("u", speech="please delete my data")
    assert r.rights_ref and "deletion request" in r.say
    assert [x["kind"] for x in g.store.rights("t1")] == ["erasure"]
    assert g.store.consent_state("t1", g.pid("u")) == {}                    # not treated as an answer

def test_hindi_flow_and_language_sticks(v):
    vg, g = v
    assert "नमस्ते" in vg.handle("u", speech="नमस्ते").say
    r = vg.handle("u", speech="हाँ"); assert "मार्केटिंग" in r.say
    assert "धन्यवाद" in vg.handle("u", speech="नहीं").say
    assert g.store.consent_state("t1", g.pid("u")) == {"order_updates": True, "marketing": False}

def test_returning_caller_skips_menu_and_dropped_call_resumes(v):
    vg, g = v
    vg.handle("u", speech="hi"); vg.handle("u", digits="1")                  # caller drops before answering marketing
    r = vg.handle("u", digits="2")                                           # next call resumes at question 2
    assert "saved" in r.say
    assert vg.handle("u", speech="book me in").action == "forward"           # consented: straight to the agent

def test_minor_text_flow_still_applies_by_voice(v):
    vg, g = v
    vg.handle("kid", speech="hi"); vg.handle("kid", digits="1"); vg.handle("kid", digits="1")
    r = vg.handle("kid", speech="I am 13 years old")
    assert r.action == "end" and "mobile number" in r.say
