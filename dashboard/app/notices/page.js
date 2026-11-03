"use client";
import { useApi, Err } from "../../lib/api";
export default function Notices() {
  const { data, err } = useApi("/v1/notices");
  return (<><h1>Notice versions</h1><Err e={err} />
    {data && <><p className="err">{data.status}</p><p>Active version: <b>{data.version}</b>. The version is stored with every consent record.</p>
      <h3>Purposes</h3><table><thead><tr><th>ID</th><th>English</th><th>Hindi</th><th>Retention (days)</th></tr></thead><tbody>{Object.entries(data.purposes).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.en}</td><td>{v.hi}</td><td>{v.retention_days}</td></tr>)}</tbody></table>
      <h3>Templates</h3>{Object.entries(data.templates).map(([k, v]) => <div className="card" key={k}><b>{k}</b><pre style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>{v.en}</pre></div>)}</>}</>);
}
