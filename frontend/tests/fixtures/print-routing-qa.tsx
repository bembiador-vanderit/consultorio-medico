import React from 'react';import {createRoot} from 'react-dom/client';
import FakePrintAction from '../../src/components/FakePrintAction';
import {api,setAccessToken} from '../../src/services/api';import '../../src/index.css';
if(!import.meta.env.DEV || location.port!=='5189' || !['localhost','127.0.0.1'].includes(location.hostname))throw Error('Isolated QA preview only');
api.defaults.baseURL='/api/v1';
const origin=innerWidth<=500?'WEB_MOBILE':innerWidth<=1024?'WEB_TABLET':'WEB_DESKTOP';
async function start(){const {data}=await api.post('/qa/session');setAccessToken(data.access_token);
 createRoot(document.getElementById('root')!).render(<main style={{maxWidth:900,margin:'auto',padding:20,minWidth:0}}><h1>Atlas · Impresión de prueba</h1><p>Entorno aislado · PostgreSQL temporal · HTTPS al backend · {origin}</p><p>Documento sintético sin información clínica o financiera.</p><FakePrintAction origin={origin}/></main>);
}start().catch(()=>{document.getElementById('root')!.textContent='QA temporal no disponible; no se contactó la base oficial.'});
