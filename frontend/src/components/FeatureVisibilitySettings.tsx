import {useEffect,useRef,useState,type FormEvent} from "react";
import {api} from "../services/api";
import {visibilityFeatures,type VisibilityFeature} from "../services/featureVisibility";
import {Alert,Button,FormField,Select,Textarea} from "../ui";
import "./featureVisibility.css";

type Item={feature_code:VisibilityFeature;context_code:"ambulatory";audience:"doctor"|"secretary";visibility_mode:"hidden"|"visible"|null;revision:number;visible:boolean;source:string};
type Settings={enabled:boolean;center_id:number|null;items:Item[];centers:{id:number;name:string}[]};
export default function FeatureVisibilitySettings(){
  const [center,setCenter]=useState(""),[settings,setSettings]=useState<Settings|null>(null),[reason,setReason]=useState("");
  const [error,setError]=useState(""),[saved,setSaved]=useState(false),[busy,setBusy]=useState(false);
  const submitting=useRef(false), request=useRef(0);
  const params=()=>center?{center_id:Number(center)}:{};
  useEffect(()=>{
    const id=++request.current;setSettings(null);setSaved(false);setError("");setReason("");
    void api.get<Settings>("/feature-visibility/settings",{params:params()}).then(({data})=>{if(id===request.current)setSettings(data);})
      .catch(()=>{if(id===request.current)setError("No fue posible consultar la visibilidad de funciones.");});
    return()=>{request.current++;};
  },[center]);
  async function save(event:FormEvent,inherit=false){
    event.preventDefault();if(!settings?.enabled||submitting.current||reason.trim().length<5)return;
    submitting.current=true;setBusy(true);setError("");setSaved(false);
    try{
      const changes=settings.items.map(({feature_code,context_code,audience,revision,visible})=>({feature_code,context_code,audience,revision,visibility_mode:inherit?null:visible?"visible":"hidden"}));
      const {data}=await api.put<Settings>("/feature-visibility/settings",{changes,reason},{params:params()});
      setSettings(data);setReason("");setSaved(true);window.dispatchEvent(new Event("atlas-feature-visibility-changed"));
    }catch{setError("No se guardó la configuración. Vuelva a cargar si otra persona la modificó.");}
    finally{submitting.current=false;setBusy(false);}
  }
  return <section className="feature-visibility-settings" aria-label="Visibilidad de funciones clínicas">
    <h3>Visibilidad de funciones clínicas</h3>
    <p>Mostrar u ocultar no concede ni retira permisos clínicos. Los datos existentes se conservan.</p>
    {error&&<Alert tone="warning" title="Visibilidad de funciones">{error}</Alert>}
    {settings&&<>
      <FormField label="Ámbito de visibilidad"><Select disabled={busy} value={center} onChange={e=>setCenter(e.target.value)}><option value="">Toda la organización</option>{settings.centers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Select></FormField>
      <p>Contexto: <strong>Consulta ambulatoria</strong></p>
      {!settings.enabled?<p>Configuración pendiente de activación de la base. Se usan los valores de visibilidad predeterminados.</p>:<form onSubmit={save}>
        {Object.entries(visibilityFeatures).map(([feature,label])=><fieldset key={feature} disabled={busy}><legend>Seguridad clínica · {label}</legend><div className="feature-visibility-options">{settings.items.filter(i=>i.feature_code===feature).map(item=><label key={item.audience}><input type="checkbox" checked={item.visible} onChange={e=>{setSettings({...settings,items:settings.items.map(i=>i===item?{...i,visible:e.target.checked}:i)});setSaved(false);}}/> {item.audience==="doctor"?"Médicos":"Secretarías"}</label>)}</div></fieldset>)}
        <p>Prioridad: centro → organización → predeterminado. Sin configuración, ambas opciones están ocultas.</p>
        <FormField label="Motivo del cambio" required><Textarea required minLength={5} maxLength={500} disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}/></FormField>
        <div className="feature-visibility-actions"><Button type="submit" disabled={busy||reason.trim().length<5}>Guardar visibilidad</Button><Button type="button" variant="outline" disabled={busy||reason.trim().length<5} onClick={event=>void save(event,true)}>{center?"Heredar organización":"Restablecer predeterminados"}</Button></div>
      </form>}
    </>}
    {saved&&<p role="status">Visibilidad guardada y auditada. Se aplicará en la próxima carga.</p>}
  </section>;
}
