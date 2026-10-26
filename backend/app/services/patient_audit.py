"""Patient diffs in the existing restricted audit store, never application logs."""
from datetime import date, datetime

from app.models.clinical_audit import ClinicalAuditLog


# Never copy clinical values or arbitrary request keys into the audit context.
REDACTED_FIELDS = {"registered_sex", "blood_type"}
DEMOGRAPHIC_FIELDS = {
    "first_name", "last_name", "date_of_birth", "phone", "email",
    "document_type", "document_number", "home_phone", "address", "country_code",
    "territorial_unit_id", "sector_locality", "province", "nationality", "occupation",
    "emergency_contact_name", "emergency_contact_relationship", "emergency_contact_mobile",
    "emergency_contact_home_phone", "guardian_name", "guardian_relationship",
    "guardian_mobile", "guardian_home_phone", "locality_id",
}


def record_patient_changes(db, actor, patient, changes):
    diff = {}
    for field, values in changes.items():
        if field in REDACTED_FIELDS:
            diff[field] = {"before": "[REDACTED]", "after": "[REDACTED]", "redacted": True}
        elif field in DEMOGRAPHIC_FIELDS:
            diff[field] = {key: value.isoformat() if isinstance(value, (date, datetime)) else value
                           for key, value in values.items()}
    if diff:
        # Patient identity is organization-wide, not owned by one arbitrary center.
        db.add(ClinicalAuditLog(organization_id=patient.organization_id, user_id=actor.id,
            resource_type="patient", resource_id=patient.id, action="patient.update",
            outcome="success", context={"changes": diff}))
