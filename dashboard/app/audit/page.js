"use client";
import { useState } from "react";
import { api } from "../../lib/api";
export default function Audit() {
  const [biz, setBiz] = useState("Your Business"); const [err, setErr] = useState("");
  const dl = async () => { try { const r = await api(`/v1/audit-pack?business=${encodeURIComponent(biz)}`); const u = URL.createObjectURL(await r.blob()); Object.assign(document.createElement("a"), { href: u, download: "audit-pack.zip" }).click(); } catch (e) { setErr(e.message); } };
  return (<><h1>Audit pack</h1><p className="muted">ZIP with consent records, processing register, rights and erasure history, ledger extract, access log and chain verification. Exporting is itself logged.</p>
    <div className="row"><input value={biz} onChange={(e) => setBiz(e.target.value)} /><button onClick={dl}>Download</button></div><p className="err">{err}</p></>);
}
