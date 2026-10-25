import {after,test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({server:{middlewareMode:true,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {api}=await server.ssrLoadModule('/src/services/api.ts');
const {listAvailableDestinations}=await server.ssrLoadModule('/src/services/agentDestinations.ts');
const original=api.defaults.adapter;
after(async()=>{api.defaults.adapter=original;await server.close()});
for(const origin_type of ['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET']) {
  test(`${origin_type} availability needs no local agent and cannot submit a job`,async()=>{
    let request;
    api.defaults.adapter=async c=>{request=c;return{data:{origin_type,origin_user:1,source_agent_required:false,availability_only:true,execution_enabled:false,destinations:[]},status:200,statusText:'OK',headers:{},config:c}};
    const result=await listAvailableDestinations({origin_type,center_id:1,paper_name:'A4'});
    assert.equal(request.method,'get');assert.equal(request.url,'/local-agents/destinations');
    assert.deepEqual(request.params,{origin_type,center_id:1,paper_name:'A4'});
    assert.equal(request.data,undefined);assert.equal(result.execution_enabled,false);assert.equal(result.source_agent_required,false);
  });
}
test('denied availability is propagated, never bypassed with device identity',async()=>{
  api.defaults.adapter=async()=>{throw{response:{status:403}}};
  await assert.rejects(()=>listAvailableDestinations({origin_type:'WEB_MOBILE'}),e=>e.response.status===403);
});
