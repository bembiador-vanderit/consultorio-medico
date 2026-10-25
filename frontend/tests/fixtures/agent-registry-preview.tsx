/** Development-only visual fixture. All requests intercepted; no credentials or official DB. */
import React from "react";
import {createRoot} from "react-dom/client";
import AgentDevices from "../../src/pages/AgentDevices";
import {api} from "../../src/services/api";
import "../../src/index.css";
if(!import.meta.env.DEV)throw Error("Development fixture only");
const user:any={id:9000,roles:["admin"],permissions:["local_agents:view","local_agents:manage"]};
const fixture={organization:{id:9000,name:"Organización sintética QA"},centers:[{id:9000,name:"Centro sintético QA"}],
 workgroups:[{id:9000,center_id:9000,name:"Grupo sintético QA — dos redes distintas"}],
 agents:[{id:9000,agent_uuid:"00000000-0000-0000-0000-000000009000",station_name:"PC Médico sintético QA",display_code:"QA-PC-01",status:"online",center_id:9000,workgroup_id:9000,version:"1.2.0-dev",protocol_version:3,last_seen_at:"2026-10-19T22:00:00Z",printers:[{id:9000,display_name:"Impresora sintética QA — nombre largo para validar composición",driver:"Driver sintético QA",is_default:true,is_virtual:false,connection:"Local",status:"Ready",available:true,papers:[{name:"A4"},{name:"Letter"}]}]},
 {id:9001,agent_uuid:"00000000-0000-0000-0000-000000009001",station_name:"PC Secretaría sintética QA",display_code:"QA-PC-02",status:"offline",center_id:9000,workgroup_id:9000,version:"1.2.0-dev",protocol_version:3,last_seen_at:"2026-10-19T21:00:00Z",printers:[]}]};
api.defaults.adapter=async config=>{
 if(config.method!=="get"||config.url!=="/local-agents/registry")throw Error("Writes and non-fixture requests blocked");
 return{config,data:fixture,status:200,statusText:"QA isolated",headers:{}};
};
createRoot(document.getElementById("root")!).render(<main style={{maxWidth:1200,margin:"auto",padding:16,minWidth:0}}><p>QA aislado · Solo lectura · Sin conexión a datos oficiales</p><AgentDevices user={user}/></main>);
