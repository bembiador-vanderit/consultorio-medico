"""Synthetic, one-time seed; refuses any database other than atlas_prepilot."""
import json
import os
from datetime import date, time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine
from app.core.security import hash_password
from app.models import Organization, OrganizationMembership, Role, User, Patient, CareCenter, Locality, Appointment, SecretaryCenterScope
from app.models.insurance import InsuranceCompany, InsurancePlan, PatientInsurance
from app.models.clinical_catalog import Specialty

assert engine.url.database == 'atlas_prepilot'
data = {}
with Session(engine) as db:
    assert db.scalar(select(Organization).where(Organization.slug == 'second')) is None, 'Seed already applied'
    db.add(Organization(id=2, slug='second', name='Atlas B — pruebas sintéticas', timezone='America/Santo_Domingo'))
    db.get(Organization,1).name = 'Atlas A — pruebas sintéticas'
    roles = {r.code:r for r in db.scalars(select(Role))}
    platform = User(email='platform@example.com', full_name='Plataforma sintética', is_platform_admin=True,
        password_hash=hash_password(os.environ['INITIAL_ADMIN_PASSWORD']),
        memberships=[OrganizationMembership(organization_id=o, roles=[roles['admin']]) for o in (1,2)])
    db.add(platform)
    for org in (1,2):
        locality=Locality(organization_id=org,name=f'Localidad sintética {org}')
        db.add(locality); db.flush()
        center=CareCenter(organization_id=org,name=f'Centro Atlas {org}',city='Prueba',locality_id=locality.id)
        db.add(center); db.flush()
        specialty=Specialty(organization_id=org,name='Medicina general sintética',code='prepilot_general')
        db.add(specialty); db.flush()
        users={}
        for role in ('admin','doctor','secretary'):
            u=User(email=f'{role}{org}@example.com',full_name=f'{role} Atlas {org}',
                password_hash=hash_password(os.environ['INITIAL_ADMIN_PASSWORD']),centers=[center],
                memberships=[OrganizationMembership(organization_id=org,roles=[roles[role]])])
            db.add(u); db.flush(); users[role]=u
        users['doctor'].specialties=[specialty]
        db.add(SecretaryCenterScope(organization_id=org,secretary_id=users['secretary'].id,center_id=center.id,manage_all_doctors=True))
        company=InsuranceCompany(organization_id=org,name=f'ARS Sintética {org}',code=f'TEST{org}')
        db.add(company); db.flush()
        plan=InsurancePlan(organization_id=org,insurance_company_id=company.id,name='Plan sintético')
        db.add(plan); db.flush()
        row={'center':center.id,'company':company.id,'plan':plan.id,'users':{r:u.id for r,u in users.items()}}
        for i,kind in enumerate(('private','insured')):
            p=Patient(organization_id=org,first_name=f'Paciente {kind} Atlas {org}',last_name='SINTÉTICO',date_of_birth=date(1990,1,1))
            db.add(p); db.flush()
            a=Appointment(organization_id=org,patient_id=p.id,doctor_id=users['doctor'].id,center_id=center.id,specialty_id=specialty.id,appointment_date=date.today(),appointment_time=time(10+i))
            db.add(a); db.flush(); row[kind]={'patient':p.id,'appointment':a.id}
            if kind=='insured':
                policy=PatientInsurance(organization_id=org,patient_id=p.id,insurance_company_id=company.id,plan_id=plan.id,plan_name=plan.name,member_number=f'SYNTHETIC-{org}',is_primary=True,valid_from=date(2026,1,1),valid_until=date(2027,12,31))
                db.add(policy); db.flush(); row[kind]['policy']=policy.id
        data[org]=row
    db.commit()
with open('/tmp/prepilot-fixture.json','w') as f:
    json.dump(data,f,indent=2)
print('Seed complete: two organizations, three local roles each, platform admin, synthetic patients and ARS.')
