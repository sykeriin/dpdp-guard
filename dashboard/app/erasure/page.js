"use client";
import { api, useApi, Table, Err } from "../../lib/api";
export default function Erasure() {
  const { data, err, reload } = useApi("/v1/erasure");
  return (<><h1>Erasure jobs</h1><Err e={err} /><div className="row"><button onClick={async () => { await api("/v1/workers/run", { method: "POST" }); reload(); }}>Run workers now</button></div>
    <Table rows={data} cols={[["id", "Job"], ["reason", "Reason"], ["status", "Status"], ["attempts", "Tries"], ["results", "Per-connector proof", (r) => r.results?.filter((x) => x.kind).map((x) => `${x.kind}:${x.ok ? "ok(" + x.deleted + ")" : "FAILED"}`).join(", ")]]} /></>);
}
