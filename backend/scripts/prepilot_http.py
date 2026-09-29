"""Integrated HTTP validation against the running disposable PostgreSQL stack."""
import json, os
from datetime import date
from uuid import uuid4
import httpx

d=json.load(open('/tmp/prepilot-fixture.json'))
results=[]
def client(org=1, role='admin'):
    c=httpx.Client(base_url='http://127.0.0.1:8000/api/v1',headers={'Host':'localhost' if org==1 else '127.0.0.1'},timeout=90)
    r=c.post('/auth/login',json={'email':f'{role}{org}@example.com','password':os.environ['INITIAL_ADMIN_PASSWORD']})
    assert r.status_code==200,r.text
    c.headers['Authorization']='Bearer '+r.json()['access_token']
    return c
def request(c,method,path,body=None,status=200):
    r=c.request(method,path,json=body)
    assert r.status_code==status,(method,path,r.status_code,r.text)
    return r.json() if r.content else None
def record(name):
    results.append({'scenario':name,'result':'PASS'}); print('PASS',name,flush=True)
def pay(register,*parts):
    return {'request_key':str(uuid4()),'register_id':register['id'],'parts':[{'method':m,'amount':v} for m,v in parts]}
clients={o:client(o) for o in (1,2)}
for org,c in clients.items():
    if os.environ.get('PREPILOT_ORG') and str(org)!=os.environ['PREPILOT_ORG']: continue
    row=d[str(org)]; other=d[str(3-org)]
    assert request(c,'GET','/organization')['id']==org
    for p in [f"/patients/{other['private']['patient']}",f"/insurance/patients/{other['insured']['patient']}",f"/finance/invoices?center_id={other['center']}",f"/ars/claims?center_id={other['center']}"]:
        request(c,'GET',p,status=404)
    assert all(x['id']!=other['company'] for x in request(c,'GET','/insurance/companies'))
    request(c,'GET','/platform/organizations',status=404)
    record(f'Tenant {org}: aislamiento pacientes/seguros/ARS/caja/contexto')
    register=request(c,'POST','/finance/registers',{'center_id':row['center'],'opening_amount':'100'},201)
    def invoice(kind,payment):
        body={'request_key':str(uuid4()),'center_id':row['center'],'patient_id':row[kind]['patient'],'appointment_id':row[kind]['appointment'],'concept':'Consulta sintética','base_amount':'1500','payment':payment}
        if kind=='insured': body['coverage_revision']=1
        return request(c,'POST','/finance/invoices',body,201)
    private=invoice('private',pay(register,('cash','200'),('card','300')))
    assert private['balance']=='1000.00' and private['ars_amount']=='0.00'
    paid=request(c,'POST',f"/finance/invoices/{private['id']}/payments",pay(register,('transfer','1000')))
    assert paid['balance']=='0.00'
    detail=request(c,'GET',f"/finance/invoices/{private['id']}")
    movement=detail['movements'][0]
    request(c,'POST',f"/finance/movements/{movement['id']}/reverse",{'register_id':register['id'],'request_key':str(uuid4()),'reason':'Reverso sintético'},201)
    assert request(c,'GET',f"/finance/invoices/{private['id']}")['balance']=='500.00'
    request(c,'POST',f"/finance/invoices/{private['id']}/payments",pay(register,('cash','500')))
    record(f'Tenant {org}: particular parcial/mixto/posterior/reverso')
    insured=row['insured']
    request(c,'PUT',f"/insurance/appointments/{insured['appointment']}/coverage",{'patient_insurance_id':insured['policy'],'service':'Consulta sintética','base_amount':'1500','covered_amount':'1000','patient_copay':'500','authorization_status':'authorized','authorization_number':'SYNTHETIC-AUTH'})
    inv=invoice('insured',pay(register,('cash','500')))
    assert inv['ars_amount']=='1000.00' and inv['balance']=='0.00'
    claim=request(c,'POST','/ars/claims',{'appointment_id':insured['appointment'],'coverage_revision':1},201)
    for state in ('pending','sent','received'):
        request(c,'POST',f"/ars/claims/{claim['id']}/transition",{'state':state})
    request(c,'POST',f"/ars/claims/{claim['id']}/glosa",{'kind':'glosed','amount':'200','code':'SYN','note':'Glosa sintética'})
    request(c,'POST',f"/ars/claims/{claim['id']}/correction",{'approved_amount':'1000','note':'Corrección sintética'})
    request(c,'POST',f"/ars/claims/{claim['id']}/transition",{'state':'resent'})
    rem=request(c,'POST','/ars/remittances',{'insurance_company_id':row['company'],'center_id':row['center'],'received_on':date.today().isoformat(),'reference':f'SYN-{org}','amount':'1000'},201)
    for amount,balance in [('400','600.00'),('600','0.00')]:
        request(c,'POST',f"/ars/remittances/{rem['id']}/apply",{'allocations':[{'claim_id':claim['id'],'amount':amount}]})
        assert request(c,'GET',f"/ars/claims/{claim['id']}")['balance']==balance
    app=request(c,'GET',f"/ars/remittances/{rem['id']}")['applications'][0]
    request(c,'POST',f"/ars/applications/{app['id']}/reverse",{'reason':'Reverso sintético'})
    assert request(c,'GET',f"/ars/claims/{claim['id']}")['balance']=='400.00'
    aging=request(c,'GET',f"/ars/receivables?center_id={row['center']}&as_of=2026-12-01")
    assert any(x['balance']=='400.00' for x in aging)
    summary=request(c,'GET',f"/ars/reconciliation?center_id={row['center']}&from_date=2026-01-01&to_date=2026-12-31")
    assert summary[0]['paid']=='600.00'
    record(f'Tenant {org}: seguro/copago/reclamación/glosa/reenvío/remesa parcial y completa/reverso/aging/conciliación')
    request(c,'POST',f"/finance/registers/{register['id']}/close",{'counted_cash':'0'},422)
    closed=request(c,'POST',f"/finance/registers/{register['id']}/close",{'counted_cash':'0','notes':'Diferencia sintética de validación'})
    assert closed['difference']!='0.00'
    record(f'Tenant {org}: cierre con diferencia exige observación')
    doc=client(org,'doctor'); secretary=client(org,'secretary')
    request(doc,'GET','/ars/claims',status=403)
    request(doc,'GET','/finance/invoices',status=403)
    request(secretary,'GET','/ars/claims',status=403)
    request(secretary,'GET',f"/finance/invoices?center_id={row['center']}")
    record(f'Tenant {org}: permisos médico y secretaria')
with open('/tmp/prepilot-http-results.json','w') as f: json.dump(results,f,indent=2,ensure_ascii=False)
