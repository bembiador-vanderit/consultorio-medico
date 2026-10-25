import {useEffect,useRef,useState} from 'react';
import {Modal,Button,FormField,Select,Input} from '../ui';
import {cancelFakePrint,printDestinations,printStatusLabel,printStatus,submitFakePrint,confirmPhysicalPrint,type FakeDestination,type PrintStatus} from '../services/printRouting';
import type {PrintOriginType} from '../services/agentDestinations';
import './fakePrintAction.css';

// Shared selector: isolated DEV API by default; official mode is authenticated SafeValidation only.
export default function FakePrintAction({origin,documentReference='qa-general',official=false}:{origin:PrintOriginType;documentReference?:string;official?:boolean}) {
 const base=official?'/print-routing':'/print-jobs';
 const [open,setOpen]=useState(false),[destinations,setDestinations]=useState<FakeDestination[]>([]),[station,setStation]=useState(''),[printer,setPrinter]=useState(''),[copies,setCopies]=useState('1');
 const [job,setJob]=useState<PrintStatus|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [lookup,setLookup]=useState(''),[confirmOpen,setConfirmOpen]=useState(false),[answer,setAnswer]=useState<boolean|null>(null);
 const intent=useRef<string|null>(null);
 useEffect(()=>{if(!open)return;let alive=true;setError('');printDestinations(base).then(rows=>{if(alive)setDestinations(rows)}).catch(()=>{if(alive)setError('No se pudieron cargar destinos autorizados.')});return()=>{alive=false};},[open,base]);
 useEffect(()=>{if(!job || !['queued','received','ready','printing','submitted'].includes(job.status))return;let alive=true;
   const timer=setInterval(()=>{printStatus(job.job_id,base).then(value=>{if(alive){setJob(value);setError('')}}).catch(()=>{if(alive)setError('Sin conexión. Se conserva el mismo trabajo; no se enviará otra copia.')});},1000);
   return()=>{alive=false;clearInterval(timer)};
 },[job?.job_id,job?.status]);
 const available=destinations.filter(d=>d.target_agent===station);
 const selected=available.find(d=>d.target_printer===printer);
 const valid=Boolean(selected?.available)&&Number.isInteger(Number(copies))&&Number(copies)>=1&&Number(copies)<=999;
 async function submit(){if(!valid||busy)return;setBusy(true);setError('');intent.current??=crypto.randomUUID();
   try{const actualOrigin=official?(window.innerWidth<=500?'WEB_MOBILE':window.innerWidth<=1024?'WEB_TABLET':'WEB_DESKTOP'):origin;setJob(await submitFakePrint({job_id:intent.current,target_agent:station,target_printer:printer,document_reference:documentReference,copies:Number(copies),origin_type:actualOrigin},base));}
   catch{setError('No se confirmó el envío. Reintentar conserva el mismo identificador; no cambies el destino.');}
   finally{setBusy(false)}
 }
 function reset(){intent.current=null;setJob(null);setPrinter('');setStation('');setCopies('1');setError('');setConfirmOpen(false);setAnswer(null);}
 async function consult(){if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(lookup))return;setBusy(true);setError('');
   try{const found=await printStatus(lookup,'/print-routing');intent.current=found.job_id;setJob(found);setConfirmOpen(false);setAnswer(null)}catch{setError('Trabajo no disponible dentro de su alcance autorizado.')}finally{setBusy(false)}}
 async function confirm(){if(!job||answer===null||busy)return;setBusy(true);setError('');
   try{setJob(await confirmPhysicalPrint(job.job_id,answer));setConfirmOpen(false);setAnswer(null)}catch{setError('No se confirmó el resultado. Consulte el estado antes de reintentar; no se enviará otra copia.')}finally{setBusy(false)}}
 const physical=job?.execution_mode==='physical_qa';
 const confirmable=official&&physical&&job?.status==='submitted'&&job.can_confirm_physical&&Number(job.result?.synthetic_spooler_id)>0;
 return <><Button onClick={()=>setOpen(true)}>Imprimir</Button><Modal open={open} onClose={()=>setOpen(false)} title={physical?'Resultado de impresión':official?'Validación de impresión · sin papel':'Impresión sintética QA'} description={physical?'Consulta y confirmación del trabajo existente. Estas acciones no imprimen otra copia.':official?'API y agente oficiales · Ejecución SafeValidation. No envía nada al spooler de Windows.':'Fake spooler · No se envía papel ni información clínica o financiera.'}
 footer={<><Button variant="outline" onClick={()=>setOpen(false)}>Cerrar</Button>{!job&&<Button disabled={!valid||busy} onClick={submit}>{busy?'Enviando…':intent.current?'Reintentar mismo trabajo':official?'Validar sin imprimir':'Enviar a fake spooler'}</Button>}</>}>
 <div className="fake-print-action">
 {!physical&&<>
 {!error&&destinations.length===0&&<p>No hay destinos autorizados disponibles. Actualice el inventario o consulte al administrador.</p>}
 <FormField label="Estación" required><Select value={station} disabled={Boolean(intent.current)} onChange={e=>{setStation(e.target.value);setPrinter('')}}><option value="">Seleccionar estación autorizada</option>{[...new Map(destinations.map(d=>[d.target_agent,d])).values()].map(d=><option key={d.target_agent} value={d.target_agent}>{d.station_name}{!(d.target_agent===station?(job?.target_online??d.online):d.online)?' · Sin conexión':''}</option>)}</Select></FormField>
 <FormField label="Impresora" required><Select value={printer} disabled={Boolean(intent.current)||!station} onChange={e=>setPrinter(e.target.value)}><option value="">{official?'Seleccionar impresora autorizada':'Seleccionar impresora fake'}</option>{available.map(d=><option disabled={!d.available} key={d.target_printer} value={d.target_printer}>{d.printer_name}{!d.available?' · No disponible':''}</option>)}</Select></FormField>
 <FormField label="Copias" description="1 a 999 · Copias simuladas"><Input type="number" min={1} max={999} step={1} value={copies} disabled={Boolean(intent.current)} onChange={e=>setCopies(e.target.value)}/></FormField>
 {selected&&!(job?.target_online??selected.online)&&(!job||job.status==='queued')&&<p>La estación está sin conexión. El trabajo permanecerá en cola hasta reconectar o expirar.</p>}
 </>}
 {job&&<section aria-live="polite" role="status"><h3>{printStatusLabel(job)}</h3><p>Trabajo: <span className="fake-job-id">{job.job_id}</span></p><p>{job.copies} copia(s) · {job.origin_type}</p>{physical&&<p>Impresora: {job.printer_name} · Recibo de Windows: {job.result?.synthetic_spooler_id??'Sin recibo'}</p>}{job.result?.error_code&&<p>{job.result.error_code}</p>}
 {['queued','received','ready'].includes(job.status)&&<Button variant="outline" onClick={async()=>{try{setJob(await cancelFakePrint(job.job_id,base))}catch{setError('No se confirmó la cancelación. Consulta el estado antes de reintentar.')}}}>Cancelar trabajo</Button>}
 {job.status==='printing'&&<p>{physical?'Ya comenzó el envío; no se promete cancelar.':'Ya comenzó la ejecución fake; no se promete cancelar.'}</p>}
 {confirmable&&!confirmOpen&&<Button onClick={()=>{setConfirmOpen(true);setAnswer(null)}}>Confirmar impresión</Button>}
 {confirmable&&confirmOpen&&<fieldset className="physical-confirmation"><legend>Confirmar resultado físico</legend><p>Compruebe la hoja antes de responder. No se imprimirá otra copia.</p>
 <Button variant="outline" aria-pressed={answer===true} onClick={()=>setAnswer(true)}>Sí, salió correctamente</Button>
 <Button variant="outline" aria-pressed={answer===false} onClick={()=>setAnswer(false)}>No salió / hubo un problema</Button>
 <Button disabled={answer===null||busy} onClick={confirm}>Guardar confirmación</Button><Button variant="outline" onClick={()=>setConfirmOpen(false)}>Cancelar confirmación</Button></fieldset>}
 {physical&&job.physical_evidence?.confirmation&&<p>{job.physical_evidence.confirmation.confirmed?'Confirmación registrada':'Usuario reportó un problema'} · Usuario {job.physical_evidence.confirmation.actor_id} · {new Date(job.physical_evidence.confirmation.at).toLocaleString()}</p>}
 {!physical&&!['queued','received','ready','printing'].includes(job.status)&&<Button variant="outline" onClick={reset}>Nueva intención de prueba</Button>}</section>}
 {official&&<details><summary>Consultar trabajo existente</summary><FormField label="Identificador del trabajo"><Input value={lookup} onChange={e=>setLookup(e.target.value)} placeholder="UUID del trabajo"/></FormField><Button variant="outline" disabled={busy||!lookup} onClick={consult}>Consultar estado</Button></details>}
 {error&&<p role="alert">{error}</p>}
 </div></Modal></>;
}
