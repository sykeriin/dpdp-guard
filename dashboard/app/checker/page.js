"use client";
import { useState } from "react";
import { BASE } from "../../lib/api";
export default function Checker() {
  const [text, setText] = useState(""); const [res, setRes] = useState(null); const [err, setErr] = useState("");
  const go = async () => { setErr(""); try { const r = await fetch(BASE + "/v1/checker", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }); if (!r.ok) throw new Error(await r.text()); setRes(await r.json()); } catch (e) { setErr(e.message); } };
  return (<><h1>Free DPDP bot checker</h1><p className="muted">Paste a transcript or bot flow. Nothing is stored. Heuristic gap report, not legal advice.</p>
    <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Bot: Hi! ...&#10;User: ..." /><div className="row"><button onClick={go} disabled={!text.trim()}>Check</button></div><p className="err">{err}</p>
    {res && <><div className="card"><div className="muted">Score</div><div className="big">{res.score}/100</div></div>
      {res.findings.map((f) => <div className="card" key={f.code}><div className={"sev-" + f.severity}>{f.severity.toUpperCase()} · {f.title}</div><div className="muted">{f.why}</div><div><b>Fix:</b> {f.fix}</div></div>)}
      <p className="muted">{res.disclaimer}</p></>}</>);
}
