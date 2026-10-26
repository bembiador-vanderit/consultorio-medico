"""0069 candidate: disposable PostgreSQL ONLY. No official activation or execution."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import engine
from app.models import User, OrganizationMembership
from app.models.print_job import PrintJob
from app.services import print_jobs as service
from app.services.tenancy import bind_scope
from test_print_job_persistence import seed_targets, intent, actor_for, progress, resolver_for

NEW_COLUMNS = ['contract_version','requested_by','origin_type','source_agent_id','document_type','document_security_class']


def guard():
    if engine.url.host != 'atlas-print69-qa-pg' or engine.url.database != 'atlas_print69_qa':
        raise RuntimeError('Disposable contract database required; official forbidden')


def fingerprints():
    with engine.connect() as db:
        result = {}
        extended = 'contract_version' in {c['name'] for c in inspect(db).get_columns('print_jobs')}
        for name in sorted(set(inspect(db).get_table_names())-{'alembic_version'}):
            projection = "to_jsonb(t)-ARRAY['"+"','".join(NEW_COLUMNS)+"']::text[]" if name=='print_jobs' and extended else 'to_jsonb(t)'
            rows = db.scalars(text(f'SELECT ({projection})::text FROM "{name}" t ORDER BY ({projection})::text'))
            result[name] = [hashlib.sha256(row.encode()).hexdigest() for row in rows]
        return result


def call(scope, action):
    with Session(engine) as db:
        bind_scope(db,'tenant',scope.organization_id)
        result=action(db); db.commit(); return result


def main():
    guard(); cfg=Config('alembic.ini')
    command.upgrade(cfg,'0068_print_job_persistence')
    targets=seed_targets(engine); scope,printer=targets[0]
    with Session(engine) as db:
        outsider=User(email='outside-contract@example.test',full_name='QA Outside',password_hash='NOT-A-LOGIN',
            memberships=[OrganizationMembership(organization_id=targets[1][0].organization_id)])
        db.add(outsider); db.commit(); outsider_id=outsider.id
    stamp=datetime.utcnow(); legacy=[str(uuid4()),str(uuid4())]
    with engine.begin() as db:
        for job,status in zip(legacy,('queued','printed')):
            db.execute(text('''INSERT INTO print_jobs(id,organization_id,center_id,agent_id,printer_id,artifact_ref,
                content_sha256,format,copies,intent_hash,status,created_at,expires_at)
                VALUES(:id,:org,:center,:agent,:printer,'legacy-qa',:sha,'plain_text',1,:sha,:state,:now,:expires)'''),
                dict(id=job,org=scope.organization_id,center=scope.center_id,agent=scope.agent_id,printer=printer,
                     sha='a'*64,state=status,now=stamp,expires=stamp+timedelta(hours=1)))
        delivery=str(uuid4())
        db.execute(text('''INSERT INTO print_deliveries VALUES(:id,:org,:job,:agent,1,:now,:lease,:now)'''),
            dict(id=delivery,org=scope.organization_id,job=legacy[1],agent=scope.agent_id,now=stamp,lease=stamp+timedelta(minutes=1)))
        db.execute(text("INSERT INTO print_results VALUES(:job,:org,:delivery,'printed',1,NULL,:now)"),
            dict(job=legacy[1],org=scope.organization_id,delivery=delivery,now=stamp))
    before=fingerprints()
    with engine.connect() as db:
        sequences=set(inspect(db).get_sequence_names()); tables=set(inspect(db).get_table_names())
    command.upgrade(cfg,'0069_print_job_contract')
    if fingerprints()!=before: raise RuntimeError('Historical fields changed during upgrade')
    with engine.connect() as db:
        if db.scalar(text('SELECT count(*) FROM print_jobs WHERE contract_version=1 AND requested_by IS NULL AND intent_hash=:hash'),{'hash':'a'*64})!=2:
            raise RuntimeError('Unsafe legacy backfill')
        if set(inspect(db).get_table_names())!=tables or set(inspect(db).get_sequence_names())!=sequences:
            raise RuntimeError('Unexpected table/sequence change')
    command.downgrade(cfg,'0068_print_job_persistence')
    if fingerprints()!=before: raise RuntimeError('Historical fields changed during downgrade')
    command.upgrade(cfg,'0069_print_job_contract')
    if fingerprints()!=before: raise RuntimeError('Historical fields changed during reapply')
    request=intent(printer)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs=list(pool.map(lambda _:call(scope,lambda db:service.register(db,scope,request,actor=actor_for(db),document_resolver=resolver_for(scope,request)).id),range(8)))
    if len(set(jobs))!=1: raise RuntimeError('Duplicate logical job')
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts=list(pool.map(lambda _:call(scope,lambda db:service.deliver(db,scope,request.job_id).id),range(8)))
    if len(set(attempts))!=1: raise RuntimeError('Duplicate live delivery')
    call(scope,lambda db:progress(db,scope,request.job_id,attempts[0]))
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(lambda _:call(scope,lambda db:service.record_result(db,scope,request.job_id,attempts[0],
            'unknown',error_code='OUTCOME_UNKNOWN').outcome),range(8)))
    if outcomes!=['unknown']*8 or call(scope,lambda db:service.deliver(db,scope,request.job_id)) is not None:
        raise RuntimeError('Unknown could replay')
    # Bypass ORM/service: direct SQL must not change intent or resurrect terminal jobs.
    for assignment in ("copies=2","origin_type='WEB_MOBILE'","status='printing'","status='received'"):
        with engine.begin() as db:
            nested=db.begin_nested()
            try:
                db.execute(text(f'UPDATE print_jobs SET {assignment} WHERE id=:id'),{'id':request.job_id})
                raise RuntimeError('DB accepted forbidden mutation')
            except IntegrityError:
                nested.rollback()
    with engine.connect() as db:
        prototype=dict(db.execute(text('SELECT * FROM print_jobs WHERE id=:id'),{'id':request.job_id}).mappings().one())
    for changed, expected_fk in (({'requested_by':outsider_id},'fk_print_requester_tenant'),
        ({'origin_type':'LOCAL_AGENT','source_agent_id':targets[1][0].agent_id},'fk_print_source_tenant')):
        with engine.begin() as db:
            nested=db.begin_nested()
            try:
                db.execute(PrintJob.__table__.insert().values(**{**prototype,'id':str(uuid4()),'status':'queued',**changed}))
                raise RuntimeError('DB accepted cross-tenant actor/source')
            except IntegrityError as exc:
                if exc.orig.diag.constraint_name!=expected_fk: raise
                nested.rollback()
    try:
        command.downgrade(cfg,'0068_print_job_persistence')
        raise RuntimeError('Lossy downgrade was accepted')
    except RuntimeError as exc:
        if not str(exc).startswith('Downgrade blocked:'): raise
    with engine.connect() as db:
        if db.scalar(text('select version_num from alembic_version'))!='0069_print_job_contract':
            raise RuntimeError('Failed downgrade was not atomic')
    # Keep the candidate schema + legacy fixtures for PG parametrized tests; new QA rows only are retired.
    with engine.begin() as db:
        db.execute(text("DELETE FROM clinical_audit_logs WHERE resource_type='print_job'"))
        db.execute(text('DELETE FROM print_results WHERE job_id=:id'),{'id':request.job_id})
        db.execute(text('DELETE FROM print_deliveries WHERE job_id=:id'),{'id':request.job_id})
        db.execute(text('DELETE FROM print_jobs WHERE id=:id'),{'id':request.job_id})
    if fingerprints()!=before: raise RuntimeError('Legacy data not preserved after QA cleanup')
    print(json.dumps({'result':'PASS','roundtrip':'0068->0069->0068->0069','historical_tables':len(before),
        'legacy_jobs_preserved':2,'legacy_deliveries_preserved':1,'legacy_results_preserved':1,
        'concurrent_create':8,'concurrent_delivery':8,'concurrent_result':8,'logical_jobs':1,
        'immutable_sql':'PASS','terminal_sql':'PASS','actor_source_fk':'PASS','lossy_downgrade':'REFUSED_ATOMICALLY','new_sequences':0,'new_tables':0}))


if __name__=='__main__': main()
