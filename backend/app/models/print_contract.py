"""Contract v2: stable names, terminal uncertainty and explicit monotonic transitions."""
STATES = ('queued', 'delivering', 'received', 'ready', 'printing', 'cancel_requested',
          'cancelled', 'expired', 'submitted', 'printed', 'failed', 'unknown')
TRANSITIONS = {
    'queued': {'received', 'delivering', 'cancelled', 'expired', 'failed', 'unknown'},
    'delivering': {'received', 'cancel_requested', 'expired', 'failed', 'unknown', 'submitted', 'printed'},
    'received': {'ready', 'cancelled', 'expired', 'failed', 'unknown'},
    'ready': {'printing', 'cancelled', 'expired', 'failed', 'unknown'},
    'printing': {'submitted', 'printed', 'unknown'},
    'submitted': {'printed', 'unknown'},
    'cancel_requested': {'cancelled', 'expired', 'failed', 'unknown', 'submitted', 'printed'},
}
IMMUTABLE = ('id', 'organization_id', 'center_id', 'agent_id', 'printer_id', 'artifact_ref',
             'content_sha256', 'format', 'copies', 'intent_hash', 'created_at', 'expires_at',
             'contract_version', 'requested_by', 'origin_type', 'source_agent_id', 'document_type',
             'document_security_class')


def may_transition(previous, target):
    return previous == target or target in TRANSITIONS.get(previous, set())
