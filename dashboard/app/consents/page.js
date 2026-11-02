"use client";
import { useApi, Table, Err } from "../../lib/api";
export default function Consents() {
  const { data, err } = useApi("/v1/consents");
  return (<><h1>Consent records</h1><p className="muted">Principals are hashed IDs. No raw phone numbers are stored here.</p><Err e={err} />
    <Table rows={data} cols={[["ts", "When", (r) => new Date(r.ts).toLocaleString()], ["principal", "Principal", (r) => r.principal.slice(0, 10) + "…"], ["purpose", "Purpose"], ["granted", "Granted", (r) => (r.granted ? "yes" : "no")], ["channel", "Channel"], ["notice_version", "Notice"]]} /></>);
}
