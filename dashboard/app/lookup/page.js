"use client";
import { useState } from "react";
import { api, Err } from "../../lib/api";
export default function Lookup() {
  const [uid, setUid] = useState(""); const [res, setRes] = useState(null); const [err, setErr] = useState("");
  const go = async () => { setErr(""); setRes(null); try { const { principal } = await api(`/v1/principals/lookup?user_id=${encodeURIComponent(uid)}`); setRes({ principal, ...(await api(`/v1/principals/${principal}/export`)) }); } catch (e) { setErr(e.message); } };
  return (<><h1>Principal lookup (access requests)</h1>
    <p className="muted">Enter the user's phone number or ID as the bot sees it. We only keep a hash; the number is not stored. Each lookup is written to the access log.</p>
    <div className="row"><input placeholder="e.g. 919876543210" value={uid} onChange={(e) => setUid(e.target.value)} /><button onClick={go} disabled={!uid}>Look up</button></div><Err e={err} />
    {res && <><div className="card"><div className="muted">Principal</div><code>{res.principal}</code></div>
      <h3>Consent history</h3>{res.consents.length ? <table><thead><tr><th>When</th><th>Purpose</th><th>Granted</th></tr></thead><tbody>{res.consents.map((c, i) => <tr key={i}><td>{new Date(c.ts).toLocaleString()}</td><td>{c.purpose}</td><td>{c.granted ? "yes" : "no"}</td></tr>)}</tbody></table> : <p className="muted">None.</p>}
      <h3>Personal data held (masked)</h3>{res.personal_data.length ? <table><thead><tr><th>Kind</th><th>Purpose</th><th>Value</th><th>Expires</th><th>Erased</th></tr></thead><tbody>{res.personal_data.map((p, i) => <tr key={i}><td>{p.kind}</td><td>{p.purpose}</td><td>{p.masked}</td><td>{new Date(p.expires_at).toLocaleDateString()}</td><td>{p.erased_at ? "yes" : "no"}</td></tr>)}</tbody></table> : <p className="muted">None.</p>}</>}</>);
}
