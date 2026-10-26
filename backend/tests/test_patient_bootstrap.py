"""Permission catalog transition and repeated bootstrap; isolated SQLite only."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Organization, OrganizationMembership, Permission, Role, User
from app.services.administration import effective_permissions
from app.services.bootstrap import seed_identity


def test_patient_catalog_transition_is_once_and_preserves_custom_roles_denials_and_read_only():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        legacy = Permission(code="patients:access", description="legacy")
        custom = Permission(code="custom:capability", description="custom")
        roles = [Role(code=code, name=code, permissions=[legacy, custom]) for code in ("admin", "doctor", "secretary", "custom")]
        db.add_all(roles)
        db.add(Organization(id=1, slug="test", name="QA"))
        db.flush()
        user = User(email="qa@example.com", full_name="QA", password_hash="synthetic", roles=[roles[2]], denied_permissions=["patients:access"])
        db.add(user)
        db.commit()
        seed_identity(db)
        assert not {"patients:view", "patients:edit"}.intersection(effective_permissions(user))
        for role in roles:
            assert {"patients:view", "patients:edit", "custom:capability"}.issubset({p.code for p in role.permissions})
        secretary = roles[2]
        secretary.permissions = [p for p in secretary.permissions if p.code != "patients:edit"]
        db.commit()
        seed_identity(db)
        assert "patients:view" in {p.code for p in secretary.permissions}
        assert "patients:edit" not in {p.code for p in secretary.permissions}
        # Withdrawing both permissions must not trigger the compatibility mapping again.
        secretary.permissions = [p for p in secretary.permissions if p.code not in {"patients:view", "patients:edit"}]
        db.commit()
        seed_identity(db)
        assert not {"patients:view", "patients:edit"}.intersection({p.code for p in secretary.permissions})
        assert user.denied_permissions == ["patients:access"]
        assert len(db.scalars(select(Permission).where(Permission.code.in_(["patients:view", "patients:edit"]))).all()) == 2
    engine.dispose()
