from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Permission, Role, User, Organization, OrganizationMembership

ROLE_PERMISSIONS = {
    "admin": ("Administrador", ["users:manage", "patients:access", "centers:access", "centers:manage", "insurance:manage", "finance:read", "finance:collect", "finance:manage", "ars:read", "ars:claim", "ars:send", "ars:glosa", "ars:payment", "ars:reconcile", "ars:report"]),
    "doctor": ("Doctor", ["patients:access", "clinical:access", "centers:access"]),
    "secretary": ("Secretaria", ["patients:access", "centers:access", "insurance:manage", "finance:read", "finance:collect"]),
}

DOCUMENT_PERMISSIONS = {
    "admin": ["clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare"],
    "secretary": ["clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare"],
    "doctor": ["clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare",
               "clinical_documents:edit_clinical", "clinical_documents:sign"],
}

FORM_ADMIN_PERMISSIONS = [
    "clinical_forms:view", "clinical_forms:create", "clinical_forms:edit_draft",
    "clinical_forms:publish", "clinical_forms:retire", "clinical_forms:assign",
]

DOCUMENT_DESIGN_PERMISSIONS = {
    "admin": ["documents:view", "documents:pdf", "documents:print", "documents:reprint", "documents:manage", "documents:publish"],
    "secretary": ["documents:view", "documents:pdf", "documents:print", "documents:reprint"],
    "doctor": [],
}

PATIENT_PERMISSIONS = {"patients:access", "patients:view", "patients:edit"}
for _name, _codes in ROLE_PERMISSIONS.values():
    _codes.extend(["patients:view", "patients:edit"])


def seed_identity(db: Session) -> None:
    # Catalog presence is the one-time transition marker, not a per-user grant.
    # Once explicit grants exist, restarting must never restore withdrawn edit.
    split_patients = db.scalar(select(Permission.id).where(Permission.code == "patients:edit")) is None
    # This code can run against the official 0054 database before 0055 activation.
    # Do not add permissions there or expose document actions before the tables exist.
    inspector = inspect(db.get_bind())
    documents_ready = inspector.has_table("preoperative_evaluations") and inspector.has_table("physical_examinations")
    forms_ready = (documents_ready and inspector.has_table("clinical_form_templates") and
                   all("template_version_id" in {column["name"] for column in inspector.get_columns(table)}
                       for table in ("preoperative_evaluations", "physical_examinations")))
    safety_ready = inspector.has_table("patient_safety_entries")
    care_ready = inspector.has_table("patient_care_relationships")
    document_design_ready = inspector.has_table("document_templates") and inspector.has_table("document_template_versions")
    agents_ready = inspector.has_table("local_agents")
    agents_catalog_existed = db.scalar(select(Permission.id).where(Permission.code == "local_agents:manage")) is not None
    document_catalog_existed = db.scalar(select(Permission.id).where(Permission.code == "documents:manage")) is not None
    care_catalog_existed = db.scalar(select(Permission.id).where(Permission.code == "patient_care:view")) is not None
    safety_catalog_existed = db.scalar(select(Permission.id).where(Permission.code == "patient_safety:edit")) is not None
    if db.get(Organization, 1) is None:
        db.add(Organization(id=1, slug="pilot", name="Organización inicial", timezone="America/Santo_Domingo"))
        db.flush()
    permissions = {}
    all_codes = {item for _, values in ROLE_PERMISSIONS.items() for item in values[1]}
    if documents_ready:
        all_codes.update(code for codes in DOCUMENT_PERMISSIONS.values() for code in codes)
    if forms_ready:
        all_codes.update(FORM_ADMIN_PERMISSIONS)
    if safety_ready:
        all_codes.update({"patient_safety:view", "patient_safety:edit"})
    if care_ready:
        all_codes.update({"patient_care:view", "patient_care:manage"})
    if document_design_ready:
        all_codes.update(code for codes in DOCUMENT_DESIGN_PERMISSIONS.values() for code in codes)
    if agents_ready:
        all_codes.update({"local_agents:view", "local_agents:manage"})
    for code in all_codes:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, description=code)
        db.add(permission)
        permissions[code] = permission

    db.flush()
    roles = {}
    for code, (name, codes) in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.code == code))
        existing = role is not None
        role = role or Role(code=code, name=name)
        document_codes = DOCUMENT_PERMISSIONS[code] if documents_ready else []
        if forms_ready and code == "secretary":
            # 0056 replaces blanket preparation rights with explicit per-user grants.
            document_codes = ["clinical_documents:view"]
        form_codes = FORM_ADMIN_PERMISSIONS if forms_ready and code == "admin" else []
        # First activation grants initial defaults once. Later restarts preserve
        # deliberate role revocations instead of silently restoring them.
        design_codes = DOCUMENT_DESIGN_PERMISSIONS[code] if document_design_ready and (not existing or not document_catalog_existed) else []
        desired = set([*codes, *document_codes, *form_codes, *design_codes])
        if agents_ready and code == "admin" and (not existing or not agents_catalog_existed):
            desired.update({"local_agents:view", "local_agents:manage"})
        if care_ready and code in {"admin", "doctor"} and (not existing or not care_catalog_existed):
            desired.add("patient_care:view")
            if code == "admin":
                desired.add("patient_care:manage")
        # Only newly provisioned doctor roles receive defaults. Existing roles
        # are mapped once when the safety catalog first becomes available.
        if safety_ready and code == "doctor":
            if not existing or (not safety_catalog_existed and not {p.code for p in role.permissions}.intersection({"patient_safety:view", "patient_safety:edit"})):
                desired.update({"patient_safety:view", "patient_safety:edit"})
        current = {item.code: item for item in role.permissions}
        if existing:
            desired -= PATIENT_PERMISSIONS
        # Preserve additional/custom grants, including an explicit view-only role.
        selected = {**current, **{item: permissions[item] for item in desired}}
        if forms_ready and code == "secretary":
            for item in ("clinical_documents:create", "clinical_documents:prepare"):
                selected.pop(item, None)
        role.permissions = list(selected.values())
        db.add(role)
        roles[code] = role

    db.flush()
    if split_patients:
        for role in db.scalars(select(Role)).all():
            granted = {item.code for item in role.permissions}
            if "patients:access" in granted and not granted.intersection({"patients:view", "patients:edit"}):
                role.permissions.extend([permissions["patients:view"], permissions["patients:edit"]])
        db.flush()
    settings = get_settings()
    if (
        settings.initial_admin_email
        and settings.initial_admin_password
        and db.scalar(select(User.id).limit(1)) is None
    ):
        db.add(
            User(
                email=settings.initial_admin_email.lower(),
                full_name=settings.initial_admin_name,
                password_hash=hash_password(settings.initial_admin_password),
                roles=[roles["admin"]],
                memberships=[OrganizationMembership(organization_id=1, state="active", roles=[roles["admin"]])],
            )
        )
    db.commit()
