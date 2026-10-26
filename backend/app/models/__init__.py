from app.models.organization import Organization, OrganizationMembership
from app.models.access_schedule import AccessException, AccessBlockedDate
from app.models.appointment import Appointment, AppointmentBookingSequence
from app.models.appointment_arrival import AppointmentArrival
from app.models.appointment_contact import AppointmentContactAttempt
from app.models.agenda_schedule import DoctorAgendaSetting, DoctorAgendaException
from app.models.queue import QueueLine, QueueSequence, QueueTicket, QueueTicketEvent
from app.models.queue_call_policy import QueueCallPolicy
from app.models.queue_display import QueueDisplay, QueueDisplayLine
from app.models.waiting_room import WaitingRoom, WaitingRoomSecretary
from app.models.provider_pause import ProviderOperationalPause
from app.models.center import CareCenter
from app.models.clinical_catalog import AnatomicalRegion, DoctorProfile, MedicalStudy, Specialty, doctor_specialties, medical_study_specialties
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_addendum import ClinicalAddendum
from app.models.clinical_order import LaboratoryOrder, LaboratoryOrderItem, LaboratoryTest, StudyOrder, StudyOrderItem
from app.models.clinical_coverage import AppointmentCoverageTransfer, ClinicalCoverage
from app.models.clinical_history import ClinicalHistory
from app.models.clinical_patient_document import PreoperativeEvaluation, PhysicalExamination
from app.models.clinical_form import ClinicalFormTemplate, ClinicalFormVersion, ClinicalFormAssignment, SecretaryDocumentGrant
from app.models.diagnosis import Diagnosis
from app.models.doctor_availability import DoctorAvailability
from app.models.follow_up import FollowUp, Notification
from app.models.cardiology import CardiologyAssessment, ClinicalFollowUpPlan, FollowUpContactAttempt
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
    "AppointmentArrival",
    "Organization", "OrganizationMembership", "DoctorAgendaSetting", "DoctorAgendaException", "QueueLine", "QueueSequence", "QueueTicket", "QueueTicketEvent", "ProviderOperationalPause",
    "Permission", "Role", "User", "Locality", "Country", "TerritorialLevel", "TerritorialUnit", "RegionalSettings", "CareCenter", "DoctorAvailability", "Patient", "InsuranceCompany",
    "PatientInsurance", "ClinicalHistory", "PreoperativeEvaluation", "PhysicalExamination", "ClinicalFormTemplate", "ClinicalFormVersion", "ClinicalFormAssignment", "SecretaryDocumentGrant", "Diagnosis", "Prescription", "RequestedTests", "VitalSigns", "Appointment", "AppointmentContactAttempt", "FollowUp", "Notification", "CommunicationLog",
    "Specialty", "AnatomicalRegion", "MedicalStudy", "DoctorProfile", "doctor_specialties", "medical_study_specialties", "SecretaryCenterScope", "ClinicalAuditLog", "ClinicalAddendum", "ClinicalCoverage", "AppointmentCoverageTransfer", "QueueCallPolicy", "QueueDisplay", "QueueDisplayLine", "WaitingRoom", "WaitingRoomSecretary", "AppointmentBookingSequence",
    "LaboratoryTest", "LaboratoryOrder", "LaboratoryOrderItem", "StudyOrder", "StudyOrderItem",
    "SpecialtyTemplate", "SpecialtyTemplateModule",
]

from app.models.administration import AdminTransfer, ReauthenticationGrant, SecurityAudit
from app.models.patient_safety import PatientSafetyEntry

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

from app.models.finance import CashRegister, Invoice, CashMovement, CardProviderSetting, CardBatch, CardBatchAudit
from app.models.document_template import DocumentTemplate, DocumentTemplateVersion, DocumentTemplateAudit
from app.models.patient_care import PatientCareRelationship
from app.models.clinical_sharing import ClinicalSharingPolicy
from app.models.feature_visibility import FeatureVisibilitySetting
from app.models.ars import ArsClaim, ArsClaimEvent, ArsRemittance, ArsApplication
from app.models.local_agent import AgentWorkgroup, LocalAgent, AgentPairingCode, AgentPrinter, AuthorizedStationScope
from app.models.print_job import PrintJob, PrintDelivery, PrintResult
from app.models.user_preference import UserPreference
