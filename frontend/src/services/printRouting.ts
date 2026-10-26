import {api} from './api';
import type {PrintOriginType} from './agentDestinations';
export type FakeDestination={target_agent:string;target_printer:string;station_name:string;printer_name:string;online:boolean;available:boolean};
export type PrintStatus={job_id:string;status:string;copies:number;origin_type:string;target_online?:boolean;
 execution_mode?:string;can_confirm_physical?:boolean;printer_name?:string;
 physical_evidence?:{kind:string;confirmation:null|{confirmed:boolean;actor_id:number;at:string;reason?:string|null}};
 result:null|{outcome:string;synthetic_spooler_id:number|null;error_code:string|null}};
export const printStateLabels:Record<string,string>={queued:'En cola',received:'Recibido',ready:'Listo',printing:'Imprimiendo',submitted:'Recibo recibido · comprobar evidencia',printed:'Trabajo completado · comprobar evidencia',failed:'Error',cancelled:'Cancelado',expired:'Expirado',unknown:'Resultado incierto · requiere revisión'};
export function printStatusLabel(job:PrintStatus):string {
 if(job.execution_mode==='safe_validation'&&job.status==='printed')return 'Validación completada (sin impresión física)';
 if(job.execution_mode==='physical_qa') {
   if(job.physical_evidence?.kind==='HUMAN_CONFIRMED_PRINTED')return 'Impresión confirmada';
   if(job.status==='submitted')return 'Enviado a la impresora · confirmar resultado';
   if(job.status==='printed')return 'Impresión completada';
   if(job.status==='unknown')return 'Resultado de impresión incierto';
 }
 return printStateLabels[job.status]||job.status;
}
export async function confirmPhysicalPrint(id:string,confirmed:boolean):Promise<PrintStatus>{return(await api.post('/print-routing/'+id+'/confirm-physical',{confirmed,...(!confirmed?{reason:'not_printed'}:{})})).data;}
export async function printDestinations(base='/print-jobs'):Promise<FakeDestination[]>{return (await api.get(base+'/destinations')).data.destinations;}
export async function submitFakePrint(request:{job_id:string;target_agent:string;target_printer:string;document_reference:string;copies:number;origin_type:PrintOriginType},base='/print-jobs'):Promise<PrintStatus>{return (await api.post(base,request)).data;}
export async function printStatus(id:string,base='/print-jobs'):Promise<PrintStatus>{return(await api.get(base+'/'+id)).data;}
export async function cancelFakePrint(id:string,base='/print-jobs'):Promise<PrintStatus>{return(await api.post(base+'/'+id+'/cancel')).data;}
