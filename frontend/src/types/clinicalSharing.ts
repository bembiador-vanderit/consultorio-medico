export const sharedResources = {clinical_history:"Historia clínica",clinical_documents:"Documentos clínicos",patient_safety:"Seguridad clínica"};
export type SharedResource = keyof typeof sharedResources;
export type SharingPolicy = {enabled:boolean;revision:number;mode:"assigned"|"active_relationship"|"same_center"|"organization";limit_to_same_center:boolean;clinical_history:boolean;clinical_documents:boolean;patient_safety:boolean};
export type SharedRecord = {id:number;kind?:string;title:string;date:string;doctor_name:string|null;status:string;read_only:true;fields:{label:string;value:unknown}[]};
export type SharedProjection = {read_only:true;resource:SharedResource;items:SharedRecord[];total:number;offset:number;limit:number};
