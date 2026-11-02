# DPDP rule -> feature (working notes, verify against primary text)
| Provision | Obligation (as summarised in the report) | Where it lives |
|---|---|---|
| s.6 + Rule 3 | Itemised notice, free/specific/unambiguous opt-in per purpose | `guard.py` consent gate; `notices/notice_v1.yaml`; bare "yes" to multi-purpose notice is rejected |
| Rule 6 | Masking, access control, logs + related data kept >= 1 year | `pii.mask`, transcripts store masked text only, `events` append-only + RLS, `access_log` |
| Rule 7 | Notify users without delay; Board report within 72h | `breach.py`, `/v1/breaches*`, dashboard Breach kit (72h clock) |
| Rule 8 + Third Schedule | Erase when purpose served | `pii_records.expires_at`, `workers.run_retention`, `run_erasure` |
| Rules 10-12 | Verifiable parental consent <18 | `minors.py` detects + blocks, shows parental-consent notice. **Verification not built** |
| Rule 14 | Access, correction, erasure, withdrawal, grievance | `intent.py`, `/v1/rights-requests`, `/v1/principals/{id}/export`, erasure jobs with proof events |
