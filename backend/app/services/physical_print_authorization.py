"""Operator-owned, single-job QA grant. Never an HTTP setting, permission or global toggle."""
import json
import os
from datetime import datetime, UTC, timedelta
from pathlib import Path
from uuid import UUID
from fastapi import HTTPException

FIELDS={'Enabled','AllowedJobId','AllowedAgentId','AllowedPrinterId','ExpectedPrinterName','PrinterFingerprint',
        'OrganizationId','CenterId','MaxCopies','IntentHash','ContentSha256','ExecutionMode','ValidFrom','ExpiresAt','PageFormat'}

def load():
    path=os.getenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE')
    if not path: return None
    try:
        source=Path(path)
        if not source.is_absolute() or source.is_symlink() or source.stat().st_size>8192: return None
        value=json.loads(source.read_bytes())
        if not isinstance(value,dict) or set(value)-FIELDS: return None
        return value
    except (OSError,ValueError): return None

def expires(grant):
    return datetime.fromisoformat(grant['ExpiresAt'].replace('Z','+00:00')).astimezone(UTC).replace(tzinfo=None)

def matches(grant, *, job_id, agent, printer, copies, origin, intent_hash=None):
    try:
        now=datetime.now(UTC)
        start=datetime.fromisoformat(grant['ValidFrom'].replace('Z','+00:00'))
        end=datetime.fromisoformat(grant['ExpiresAt'].replace('Z','+00:00'))
        return (grant['Enabled'] is True and grant['ExecutionMode']=='PhysicalQa'
            and UUID(grant['AllowedJobId']).int!=0 and str(UUID(grant['AllowedJobId']))==str(job_id)
            and str(UUID(grant['AllowedAgentId']))==agent.agent_uuid
            and grant['OrganizationId']==agent.organization_id and grant['CenterId']==agent.center_id
            and grant['AllowedPrinterId']==printer.local_id and not printer.is_virtual
            and (grant.get('ExpectedPrinterName') is None or grant['ExpectedPrinterName']==printer.display_name)
            and type(grant['MaxCopies']) is int and grant['MaxCopies']==copies==1 and origin=='WEB_DESKTOP'
            and start<=now<end and timedelta(0)<end-start<=timedelta(minutes=5)
            and all(isinstance(grant.get(k),str) and len(grant[k])==64
                and all(c in '0123456789abcdef' for c in grant[k]) for k in ['IntentHash','ContentSha256','PrinterFingerprint'])
            and (intent_hash is None or grant['IntentHash']==intent_hash))
    except (KeyError,TypeError,ValueError,AttributeError): return False

def require(grant, **values):
    if not matches(grant,**values): raise HTTPException(403,'Autorización física QA no disponible para este trabajo')
