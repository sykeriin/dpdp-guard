from dpdp_guard import pii, minors

def test_extract_kinds():
    t = "call 9876543210, mail a.b@x.com, PAN ABCDE1234F, aadhaar 1234 5678 9012, pin 560001, upi raj@okaxis"
    kinds = sorted(f.kind for f in pii.extract(t))
    assert kinds == ["aadhaar", "email", "pan", "phone", "pin", "upi"]

def test_masking_hides_values():
    m = pii.mask("my number is +91 98765 43210 and email raj@gmail.com")
    assert "98765" not in m and "raj@" not in m and "[PHONE:" in m and "[EMAIL:" in m

def test_no_overlap_aadhaar_not_phone():
    kinds = [f.kind for f in pii.extract("1234 5678 9012")]
    assert kinds == ["aadhaar"]

def test_order_number_not_pii():
    assert pii.extract("my order id is 12345") == []

def test_minor():
    assert minors.likely_minor("I am 15 years old") and minors.likely_minor("main class 10 mein hu")
    assert not minors.likely_minor("I am 25 years old") and not minors.likely_minor("hello")
