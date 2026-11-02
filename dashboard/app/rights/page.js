"use client";
import { useState } from "react";
import { api, useApi, Table, Err } from "../../lib/api";
export default function Rights() {
  const { data, err, reload } = useApi("/v1/rights-requests"); const [msg, setMsg] = useState("");
  const run = async (ref) => { try { await api(`/v1/rights-requests/${ref}/execute`, { method: "POST" }); setMsg(`Queued ${ref}`); reload(); } catch (e) { setMsg(e.message); } };
  return (<><h1>Rights request queue</h1><Err e={err} /><p className="muted">{msg}</p>
    <Table rows={data} cols={[["created_at", "When", (r) => new Date(r.created_at).toLocaleString()], ["ref", "Ref"], ["kind", "Type"], ["status", "Status"], ["detail", "Message (masked)"],
      ["a", "", (r) => r.status === "open" ? <button onClick={() => run(r.ref)}>{["erasure", "withdraw"].includes(r.kind) ? "Approve & erase" : "Mark done"}</button> : null]]} /></>);
}
