"use client";
import { useState } from "react";
import { api, useApi, Table, Err } from "../../lib/api";
const KINDS = ["webhook", "pgvector", "sql", "gsheets", "hubspot", "zoho", "pinecone"];
const UNVERIFIED = ["hubspot", "zoho", "pinecone", "gsheets"];
export default function Connectors() {
  const { data, err, reload } = useApi("/v1/connectors"); const [f, setF] = useState({ kind: "webhook", name: "", config: "{}" }); const [msg, setMsg] = useState("");
  const add = async () => { try { await api("/v1/connectors", { method: "POST", body: JSON.stringify({ kind: f.kind, name: f.name || null, config: JSON.parse(f.config) }) }); setMsg("Added"); reload(); } catch (e) { setMsg(e.message); } };
  const del = async (id) => { await api(`/v1/connectors/${id}`, { method: "DELETE" }); reload(); };
  return (<><h1>Erasure connectors</h1><Err e={err} />
    <p className="muted">Where erasure jobs delete data. The built-in transcript store always runs. Stored secrets are never shown again. Customers must tag records in these systems with the principal hash.</p>
    <div className="card"><div className="row"><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select>
      <input placeholder="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
      {UNVERIFIED.includes(f.kind) && <p className="err">This connector is untested against the live service. Try it on test data first.</p>}
      <textarea style={{ minHeight: 90 }} value={f.config} onChange={(e) => setF({ ...f, config: e.target.value })} placeholder='{"url": "...", "secret": "..."}' />
      <div className="row"><button onClick={add}>Add connector</button><span className="muted">{msg}</span></div></div>
    <Table rows={data} cols={[["id", "ID"], ["kind", "Kind"], ["name", "Name"], ["config_keys", "Config set", (r) => r.config_keys.join(", ")], ["x", "", (r) => <button onClick={() => del(r.id)}>Remove</button>]]} /></>);
}
