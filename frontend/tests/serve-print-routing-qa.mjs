import{createServer}from'vite';import{Agent}from'node:https';import{readFileSync}from'node:fs';
if(!process.env.ATLAS_ROUTING_QA_CA)throw Error('Ephemeral QA CA required');
const server=await createServer({configFile:false,plugins:[(await import('@vitejs/plugin-react')).default(),(await import('@tailwindcss/vite')).default()],
 server:{host:'127.0.0.1',port:5189,strictPort:true,proxy:{'/api/v1':{target:'https://localhost:18469',changeOrigin:true,secure:true,agent:new Agent({ca:readFileSync(process.env.ATLAS_ROUTING_QA_CA)})}}}});
await server.listen();console.log('QA preview http://127.0.0.1:5189/tests/fixtures/print-routing-qa.html');
for(const signal of['SIGINT','SIGTERM'])process.on(signal,async()=>{await server.close();process.exit(0)});
