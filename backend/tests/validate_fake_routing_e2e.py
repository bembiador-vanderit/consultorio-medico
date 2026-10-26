"""Manual HTTPS/PostgreSQL/.NET process E2E. Isolated QA ports/DB only; never native printing.

Run on Windows after the explicit routing_qa_app fixture, with its ephemeral CA.
No credentials are emitted. All records are disposable synthetic fixtures.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from uuid import UUID, uuid4

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=Path(os.environ['ATLAS_FAKE_ROUTING_EVIDENCE']).resolve()
DATA=EVIDENCE/'agent'
STATION=str(UUID(os.environ['ATLAS_QA_EXISTING_STATION']))  # disposable DB fixture only
BASE='https://localhost:18469/api/v1/'
CTX=ssl.create_default_context(cafile=str(EVIDENCE/'certs/ca.pem'))
DEVICE=os.environ['ATLAS_FAKE_AGENT_TOKEN']
USER=None
checks={}
jobs={}


def request(path,body=None,device=False,expected=200):
    token=DEVICE if device else USER
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,context=CTX,timeout=15) as response:
            code=response.status; raw=response.read()
    except urllib.error.HTTPError as error:
        code=error.code;raw=error.read()
    assert code==expected,(path,code,expected,raw[:300])
    return json.loads(raw) if raw else None


def control(code):
    # Docker target and the DB guard are fixed. This cannot operate on official Atlas.
    prefix='from tests.routing_qa_app import require_disposable; require_disposable(); from app.db import engine; from sqlalchemy import text; '
    result=subprocess.run(['docker','exec','atlas-routing-qa-api','python','-c',prefix+code],capture_output=True,text=True,check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def presence(online=True,available=None):
    printer_change="c.execute(text('update agent_printers set available=:ok'),{'ok':"+str(available)+"}); " if available is not None else ''
    control("from datetime import datetime,timedelta; c=engine.connect(); c.execute(text('update local_agents set last_seen_at=:seen,health=:health'),{'health':'online','seen':datetime.utcnow()-timedelta(seconds="+('0' if online else '3600')+")}); "+printer_change+"c.commit()")


def create(name,**changes):
    payload=dict(job_id=str(uuid4()),target_agent=STATION,target_printer='printer-fake',document_reference='qa-general',origin_type='WEB_DESKTOP',copies=1,ttl_seconds=300)
    payload.update(changes)
    value=request('print-jobs',payload);jobs[name]=value['job_id']
    return payload,value


def delivery(job):return request(f'print-jobs/device/{job}/delivery',device=True)
def status(job):return request(f'print-jobs/{job}')
def executions(job):
    path=DATA/'fake-executions.jsonl'
    return sum(json.loads(line)['JobId']==job for line in path.read_text().splitlines()) if path.exists() else 0


def run(job,**options):
    presence()  # explicit QA reconnect before each short-lived process
    args=['dotnet',str(ROOT/'agent/Atlas.LocalAgent.RoutingQa/bin/Debug/net10.0-windows/Atlas.LocalAgent.RoutingQa.dll'),
        '--endpoint','https://localhost:18469/','--data-dir',str(DATA),'--ca',str(EVIDENCE/'certs/ca.pem'),'--station',STATION,'--job-id',job]
    for key,value in options.items():args+=['--'+key.replace('_','-'),str(value)]
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,(job,result.stderr[-1500:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    global USER
    assert (DATA/'FAKE_ROUTING_QA_ONLY').exists()
    USER=request('qa/session',{})['access_token']
    presence(available=True)
    # Real HTTPS, two HTTP creators, duplicate callbacks and new .NET process / SQLite reopen.
    payload,row=create('concurrent',copies=999)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        values=list(pool.map(lambda _:request('print-jobs',payload),range(2)))
    assert {x['job_id'] for x in values}=={row['job_id']}
    r=run(row['job_id'],duplicates=2)
    assert (r['Status'],r['Calls'],executions(row['job_id']))==('printed',1,1)
    assert run(row['job_id'])['Calls']==0
    assert executions(row['job_id'])==1
    checks['duplicate_concurrent_restart']='PASS'
    request('print-jobs',dict(payload,copies=2),expected=409)
    checks['immutable_conflict_409']='PASS'

    _,row=create('lost_response')
    assert run(row['job_id'],lose_result_once=1)['Status']=='response_lost'
    assert status(row['job_id'])['status']=='printing'
    assert run(row['job_id'])['Calls']==0
    assert status(row['job_id'])['status']=='printed' and executions(row['job_id'])==1
    checks['lost_response_restart_receipt']='PASS'

    for outcome,expected,calls in [('Unknown','unknown',1),('Timeout','unknown',1),('Failed','failed',0),('Accepted','submitted',1)]:
        _,row=create(outcome)
        r=run(row['job_id'],outcome=outcome)
        assert (r['Status'],r['Calls'])==(expected,calls)
        assert run(row['job_id'])['Calls']==0
        assert executions(row['job_id'])==calls and status(row['job_id'])['status']==expected
        checks[outcome]='PASS'

    for stage in ['queued','received','ready']:
        _,row=create('cancel_'+stage);d=delivery(row['job_id'])
        if stage!='queued':request(f"print-jobs/device/{row['job_id']}/progress",dict(delivery_id=d['delivery_id'],status='received'),device=True)
        if stage=='ready':request(f"print-jobs/device/{row['job_id']}/progress",dict(delivery_id=d['delivery_id'],status='ready'),device=True)
        assert request(f"print-jobs/{row['job_id']}/cancel",{})['status']=='cancelled'
        assert run(row['job_id'])['Calls']==0 and executions(row['job_id'])==0
        checks['cancel_'+stage]='PASS'

    presence();_,row=create('expired',ttl_seconds=5);assert delivery(row['job_id']) is not None;time.sleep(5.2)
    assert status(row['job_id'])['status']=='expired'
    assert run(row['job_id'])['Calls']==0 and executions(row['job_id'])==0
    checks['expired']='PASS'

    presence(False);_,row=create('offline')
    assert request('print-jobs/device/poll',device=True) is None
    assert status(row['job_id'])['status']=='queued'
    presence();assert run(row['job_id'])['Status']=='printed'
    checks['offline_reconnect']='PASS'

    _,row=create('unavailable');presence(available=False)
    assert run(row['job_id'])['Status']=='failed' and executions(row['job_id'])==0
    assert status(row['job_id'])['result']['error_code']=='PRINTER_UNAVAILABLE'
    presence(available=True);checks['printer_unavailable_no_fallback']='PASS'

    for ref,classification in [('qa-general','GENERAL'),('qa-financial','FINANCIAL'),('qa-clinical','CLINICAL')]:
        _,row=create(ref,document_reference=ref)
        assert row['security_class']==classification and run(row['job_id'])['Status']=='printed'
    checks['synthetic_security_classes']='PASS'
    request('print-jobs',dict(payload,job_id=str(uuid4()),target_agent=str(uuid4())),expected=404)
    for copies in [0,1000,-1,1.5,'2',True]:
        request('print-jobs',dict(payload,job_id=str(uuid4()),copies=copies),expected=422)
    request('print-jobs',dict(payload,job_id=str(uuid4()),document_reference='C:/patient.pdf'),expected=422)
    checks['unauthorized_target_copies_no_paths']='PASS'

    evidence=control("import json; c=engine.connect(); print(json.dumps({'jobs':[dict(r) for r in c.execute(text('select id,status,origin_type,document_security_class,copies,source_agent_id,intent_hash from print_jobs order by created_at')).mappings()], 'audit':[dict(r) for r in c.execute(text(\"select action,context,user_id,organization_id,center_id,created_at::text as timestamp from clinical_audit_logs where resource_type='print_job' order by id\")).mappings()], 'results':[dict(r) for r in c.execute(text('select job_id,outcome,spool_id,error_code from print_results')).mappings()]}))")
    for name,job in jobs.items():
        records=[a for a in evidence['audit'] if a['context']['job_id']==job]
        assert sum(a['action']=='print_job.created' for a in records)==1,name
        assert all(a['user_id'] and a['organization_id']==1 and a['center_id']==1 for a in records)
    assert all(row['source_agent_id'] is None for row in evidence['jobs'])
    checks['audit_actor_context_origin_target']='PASS'
    output=dict(result='PASS',checks=checks,jobs=jobs,evidence=evidence,physical_prints_sent=0)
    (EVIDENCE/'e2e-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(dict(result='PASS',checks=checks,job_count=len(jobs),physical_prints_sent=0)))


if __name__=='__main__':main()
