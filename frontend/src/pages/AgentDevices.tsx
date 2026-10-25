import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";
import { Modal } from "../ui/overlays";
import "./agentDevices.css";
import PrintAction from '../components/FakePrintAction';

type Printer = { id:number; display_name:string; driver:string|null; is_virtual:boolean; available:boolean; is_default:boolean; connection:string; status:string; papers:Record<string,unknown>[] };
type Station = { id:number; agent_uuid:string; display_code:string; station_name:string; status:string; center_id:number; workgroup_id:number; version:string; protocol_version:number; last_seen_at:string; printers:Printer[] };
type Registry = { organization:{id:number;name:string}; centers:{id:number;name:string}[]; workgroups:{id:number;name:string;center_id:number}[]; agents:Station[] };
const labels:Record<string,string> = { online:"En línea", offline:"Sin conexión", degraded:"Degradado", revoked:"Revocado" };
const errorText = (error:unknown) => (error as {response?:{status?:number}})?.response?.status === 503
  ? "Registro pendiente de activación. No se realizarán cambios en esta base." : "No fue posible completar la operación. Verifique sus permisos y vuelva a cargar.";

export default function AgentDevices({user}:{user:User}) {
  const canView = !!user.permissions?.includes("local_agents:view");
  const canManage = !!user.permissions?.includes("local_agents:manage");
  const [data,setData] = useState<Registry|null>(null);
  const [error,setError] = useState(""); const [busy,setBusy] = useState(false);
  const [center,setCenter] = useState(""); const [group,setGroup] = useState(""); const [name,setName] = useState("");
  const [pair,setPair] = useState<{code:string;expires_at:string}|null>(null);
  const [selected,setSelected] = useState<number|null>(null);
  const [revoke,setRevoke] = useState<number|null>(null); const [reason,setReason] = useState("");
  async function load(){const {data:next}=await api.get<Registry>("/local-agents/registry");setData(next);}
  async function action(work:()=>Promise<void>){setBusy(true);setError("");try{await work();}catch(e){setPair(null);setError(errorText(e));}finally{setBusy(false);}}
  useEffect(()=>{if(canView)void action(load);},[canView]);
  // One-time codes remain only in component memory, never local/session storage.
  useEffect(()=>{if(!pair)return;const timer=window.setTimeout(()=>setPair(null),Math.max(0,Date.parse(pair.expires_at)-Date.now()));return()=>window.clearTimeout(timer);},[pair]);
  if(!canView)return <p role="alert">No tiene permiso para ver estaciones.</p>;
  const station=data?.agents.find(s=>s.id===selected);
  return <section className="agent-registry" aria-label="Agentes y dispositivos">
    <header><div><p>Administración · {data?.organization.name ?? "Organización"}</p><h1>Agentes y dispositivos</h1><p>Organización → Centro → Grupo → Estación</p></div><button disabled={busy} onClick={()=>void action(load)}>Actualizar</button></header>
    <p className="agent-registry-notice">Registro y validación de routing sin papel. No habilita impresión física ni acceso clínico. Compartir red o grupo no concede autorización.</p>
    {user.permissions?.includes('documents:print')&&<section className="agent-registry-card" aria-label="Validación de routing"><h2>Validación de impresión</h2><p>Documento sintético · SafeValidation · 0 hojas. La impresora es destino lógico; no se envía nada a Windows.</p><PrintAction official origin="WEB_DESKTOP"/></section>}
    {error&&<p role="alert">{error}</p>}
    {canManage&&data&&<section aria-label="Vincular estación" className="agent-registry-card">
      <h2>Vincular estación</h2><p>El código vence en cinco minutos y solo puede utilizarse una vez.</p>
      <div className="agent-registry-fields"><label>Centro<select value={center} onChange={e=>{setCenter(e.target.value);setGroup("");setPair(null);}}><option value="">Seleccione centro</option>{data.centers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Grupo de trabajo<select value={group} onChange={e=>{setGroup(e.target.value);setPair(null);}}><option value="">Seleccione grupo</option>{data.workgroups.filter(g=>String(g.center_id)===center).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
      <button disabled={busy||!group} onClick={()=>void action(async()=>{setPair(null);const {data:code}=await api.post("/local-agents/pairing-codes",{workgroup_id:Number(group)});setPair(code);})}>Crear código de emparejamiento</button></div>
      <details><summary>Crear grupo de trabajo</summary><div className="agent-registry-fields"><label>Nombre del grupo<input maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></label><button disabled={busy||!center||!name.trim()} onClick={()=>void action(async()=>{await api.post("/local-agents/workgroups",{center_id:Number(center),name:name.trim()});setName("");await load();})}>Crear grupo</button></div></details>
      {pair&&<div role="status" className="agent-registry-code"><span>Introduzca este código únicamente en Atlas Local Agent:</span><strong>{pair.code}</strong><span>Vence: {new Date(pair.expires_at).toLocaleTimeString()}</span><button onClick={()=>setPair(null)}>Ocultar código</button></div>}
    </section>}
    {data&&data.agents.length===0&&<p>No hay estaciones registradas en esta organización.</p>}
    {data?.centers.map(c=><section key={c.id} aria-label={c.name}><h2>{c.name}</h2>{data.workgroups.filter(g=>g.center_id===c.id).map(g=><div key={g.id} className="agent-registry-group"><h3>{g.name}</h3><div className="agent-registry-grid">{data.agents.filter(s=>s.workgroup_id===g.id).map(s=><article key={s.id} className="agent-registry-card"><h3>{s.station_name}</h3><span className={`agent-registry-state agent-registry-state--${s.status}`}>{labels[s.status]??s.status}</span><dl><dt>Agent ID</dt><dd>{s.agent_uuid}</dd><dt>Versión / protocolo</dt><dd>{s.version} / {s.protocol_version}</dd><dt>Última conexión</dt><dd>{new Date(s.last_seen_at).toLocaleString()}</dd><dt>Impresoras</dt><dd>{s.printers.length}</dd></dl><button onClick={()=>setSelected(s.id)}>Ver estación e impresoras</button>{canManage&&s.status!=="revoked"&&<button onClick={()=>{setRevoke(s.id);setReason("");}}>Revocar</button>}</article>)}</div></div>)}</section>)}
    {station&&<Modal open title={`Estación ${station.station_name}`} onClose={()=>setSelected(null)} className="agent-registry-modal"><div className="agent-registry"><p>{labels[station.status]} · {station.display_code}</p><p>Catálogo de solo lectura. No se enviarán trabajos.</p>{station.printers.map(p=><article key={p.id} className="agent-registry-card"><h3>{p.display_name}</h3><p>{p.is_virtual?"Virtual":"Física / driver Windows"} · {p.available?"Disponible en último inventario":"No disponible"}{p.is_default?" · Predeterminada":""}</p><p>{p.driver??"Driver no informado"} · {p.connection}</p><p>{p.status}</p><details><summary>Formatos anunciados ({p.papers.length})</summary><ul>{p.papers.map((paper,i)=><li key={i}>{String(paper.name??"Papel")}</li>)}</ul></details></article>)}</div></Modal>}
    {revoke!==null&&<Modal open title="Revocar estación" onClose={()=>setRevoke(null)} closeDisabled={busy} className="agent-registry-modal"><div className="agent-registry"><p>Se rechazará su credencial, heartbeat e inventario. No elimina el historial.</p><label>Motivo<textarea value={reason} maxLength={300} onChange={e=>setReason(e.target.value)}/></label><button disabled={busy} onClick={()=>setRevoke(null)}>Cancelar</button><button disabled={busy||reason.trim().length<5} onClick={()=>void action(async()=>{await api.post(`/local-agents/${revoke}/revoke`,{reason:reason.trim()});setRevoke(null);await load();})}>Confirmar revocación</button></div></Modal>}
  </section>;
}
