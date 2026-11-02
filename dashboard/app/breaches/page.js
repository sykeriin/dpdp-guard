"use client";
import { useState } from "react";
import { api, useApi, Table, Err } from "../../lib/api";
export default function Breaches() {
  const { data, err, reload } = useApi("/v1/breaches"); const [f, setF] = useState({ title: "", description: "" }); const [out, setOut] = useState("");
  const create = async () => { await api("/v1/breaches", { method: "POST", body: JSON.stringify(f) }); setF({ title: "", description: "" }); reload(); };
  const report = async (id) => { const r = await api(`/v1/breaches/${id}/board-report?business=Your%20Business`); setOut(await r.text()); };
  return (<><h1>Breach kit</h1><Err e={err} /><p className="muted">Rule 7: notify affected users without delay; detailed report to the Board within 72 hours. Drafts only, have counsel review.</p>
    <div className="card"><div className="row"><input placeholder="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /><input placeholder="What happened" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /><button onClick={create} disabled={!f.title}>Open incident</button></div></div>
    <Table rows={data} cols={[["title", "Incident"], ["status", "Status"], ["c", "72h clock", (r) => r.board_report_filed_at ? "filed" : r.countdown.overdue ? "OVERDUE" : r.countdown.hours_left + "h left"],
      ["a", "", (r) => <button onClick={() => report(r.id)}>Board report draft</button>]]} />
    {out && <pre className="card" style={{ whiteSpace: "pre-wrap" }}>{out}</pre>}</>);
}
