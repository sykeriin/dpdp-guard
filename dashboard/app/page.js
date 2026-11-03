"use client";
import { useState, useEffect } from "react";
import { useApi, Err } from "../lib/api";
export default function Overview() {
  const [key, setKey] = useState(""); const [logged, setLogged] = useState(null); const [msg, setMsg] = useState("");
  useEffect(() => { fetch("/api/login").then((r) => r.json()).then((j) => setLogged(j.loggedIn)); }, []);
  const on = logged === true;
  const v = useApi("/v1/ledger/verify", [on]); const rights = useApi("/v1/rights-requests", [on]); const er = useApi("/v1/erasure", [on]); const br = useApi("/v1/breaches", [on]);
  const login = async () => { const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) }); const j = await r.json(); if (r.ok) { setKey(""); setMsg(""); setLogged(true); } else setMsg(j.error); };
  const logout = async () => { await fetch("/api/login", { method: "DELETE" }); location.reload(); };
  const open = rights.data?.filter((r) => r.status !== "fulfilled").length; const queued = er.data?.filter((j) => j.status !== "done").length;
  const urgent = br.data?.filter((b) => !b.board_report_filed_at).map((b) => b.countdown);
  return (<><h1>Overview</h1>
    <div className="card">{on ? <div className="row"><span className="ok">Logged in</span><button onClick={logout}>Log out</button></div> :
      <div className="row"><input placeholder="API key (dg_…)" value={key} onChange={(e) => setKey(e.target.value)} type="password" autoComplete="off" />
        <button onClick={login} disabled={!key}>Log in</button></div>}<p className="err">{msg}</p>{on && <Err e={v.err} />}</div>
    {on && <div className="grid">
      <div className="card"><div className="muted">Ledger integrity</div><div className={"big " + (v.data?.ok ? "ok" : "err")}>{v.data ? (v.data.ok ? "Verified" : "BROKEN") : "—"}</div><div className="muted">{v.data?.events ?? 0} events</div></div>
      <div className="card"><div className="muted">Open rights requests</div><div className="big">{open ?? "—"}</div></div>
      <div className="card"><div className="muted">Pending erasure jobs</div><div className="big">{queued ?? "—"}</div></div>
      <div className="card"><div className="muted">Breach reports to file</div><div className={"big " + (urgent?.some((c) => c.overdue) ? "err" : "")}>{urgent?.length ?? "—"}</div></div>
    </div>}</>);
}
