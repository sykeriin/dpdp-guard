"use client";
import { useState, useEffect } from "react";
import { useApi, Err } from "../lib/api";
export default function Overview() {
  const [key, setKey] = useState(""); useEffect(() => setKey(localStorage.getItem("dg_key") || ""), []);
  const v = useApi("/v1/ledger/verify", [key]); const rights = useApi("/v1/rights-requests", [key]); const er = useApi("/v1/erasure", [key]); const br = useApi("/v1/breaches", [key]);
  const open = rights.data?.filter((r) => r.status !== "fulfilled").length; const queued = er.data?.filter((j) => j.status !== "done").length;
  const urgent = br.data?.filter((b) => !b.board_report_filed_at).map((b) => b.countdown);
  return (<><h1>Overview</h1>
    <div className="card"><div className="row"><input placeholder="API key (dg_…)" value={key} onChange={(e) => setKey(e.target.value)} type="password" />
      <button onClick={() => { localStorage.setItem("dg_key", key); location.reload(); }}>Save key</button></div><Err e={v.err} /></div>
    <div className="grid">
      <div className="card"><div className="muted">Ledger integrity</div><div className={"big " + (v.data?.ok ? "ok" : "err")}>{v.data ? (v.data.ok ? "Verified" : "BROKEN") : "—"}</div><div className="muted">{v.data?.events ?? 0} events</div></div>
      <div className="card"><div className="muted">Open rights requests</div><div className="big">{open ?? "—"}</div></div>
      <div className="card"><div className="muted">Pending erasure jobs</div><div className="big">{queued ?? "—"}</div></div>
      <div className="card"><div className="muted">Breach reports to file</div><div className={"big " + (urgent?.some((c) => c.overdue) ? "err" : "")}>{urgent?.length ?? "—"}</div></div>
    </div></>);
}
