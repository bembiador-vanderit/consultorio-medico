from app.models.organization import Organization, OrganizationMembership
from app.models.access_schedule import AccessException, AccessBlockedDate
from app.models.appointment import Appointment
from app.models.center import CareCenter
from app.models.clinical_catalog import AnatomicalRegion, DoctorProfile, MedicalStudy, Specialty, doctor_specialties, medical_study_specialties
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_addendum import ClinicalAddendum
from app.models.clinical_order import LaboratoryOrder, LaboratoryOrderItem, LaboratoryTest, StudyOrder, StudyOrderItem
from app.models.clinical_coverage import AppointmentCoverageTransfer, ClinicalCoverage
from app.models.clinical_history import ClinicalHistory
from app.models.diagnosis import Diagnosis
from app.models.doctor_availability import DoctorAvailability
from app.models.follow_up import FollowUp, Notification
from app.models.communication_log import CommunicationLog
from app.models.identity import Permission, Role, User
from app.models.insurance import InsuranceCompany, PatientInsurance, InsurancePlan, AppointmentCoverage
from app.models.locality import Locality
from app.models.regional import Country, RegionalSettings, TerritorialLevel, TerritorialUnit
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.requested_tests import RequestedTests
from app.models.secretary_scope import SecretaryCenterScope
from app.models.specialty_template import SpecialtyTemplate, SpecialtyTemplateModule
from app.models.vital_signs import VitalSigns

__all__ = [
    "Organization", "OrganizationMembership",
    "Permission", "Role", "User", "Locality", "Country", "TerritorialLevel", "TerritorialUnit", "RegionalSettings", "CareCenter", "DoctorAvailability", "Patient", "InsuranceCompany",
    "PatientInsurance", "ClinicalHistory", "Diagnosis", "Prescription", "RequestedTests", "VitalSigns", "Appointment", "FollowUp", "Notification", "CommunicationLog",
    "Specialty", "AnatomicalRegion", "MedicalStudy", "DoctorProfile", "doctor_specialties", "medical_study_specialties", "SecretaryCenterScope", "ClinicalAuditLog", "ClinicalAddendum", "ClinicalCoverage", "AppointmentCoverageTransfer",
    "LaboratoryTest", "LaboratoryOrder", "LaboratoryOrderItem", "StudyOrder", "StudyOrderItem",
    "SpecialtyTemplate", "SpecialtyTemplateModule",
]

from app.models.administration import AdminTransfer, ReauthenticationGrant, SecurityAudit

from app.services import tenancy  # Register session boundary enforcement.

# Tenant-owned catalogs can use the same human labels in different organizations.
from sqlalchemy import Index
for _model, _columns in (
    (Locality, ("name",)), (InsuranceCompany, ("name",)), (InsuranceCompany, ("code",)),
    (Specialty, ("name",)), (MedicalStudy, ("canonical_key",)),
    (LaboratoryTest, ("code",)), (LaboratoryTest, ("name",)), (DoctorProfile, ("user_id",)),
    (RegionalSettings, ()),
):
    Index("uq_tenant_" + _model.__tablename__ + "_" + ("_".join(_columns) or "singleton"),
          _model.__table__.c.organization_id, *[_model.__table__.c[name] for name in _columns], unique=True)

from app.models.finance import CashRegister, Invoice, CashMovement
