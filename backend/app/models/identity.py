from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Column, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship, object_session
from sqlalchemy.ext.hybrid import hybrid_property
from app.db import Base
user_roles = Table("user_roles", Base.metadata, Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True))
role_permissions = Table("role_permissions", Base.metadata, Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True), Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True))
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    identity_active: Mapped[bool] = mapped_column("is_active", Boolean, default=True)
    session_version: Mapped[int] = mapped_column(default=0, server_default="0")
    legacy_denied_permissions: Mapped[list[str]] = mapped_column("denied_permissions", JSON, default=list)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reauth_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    reauth_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    legacy_roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users")
    centers: Mapped[list["CareCenter"]] = relationship(secondary="user_centers", back_populates="users")
    specialties: Mapped[list["Specialty"]] = relationship(secondary="doctor_specialties")
    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    def tenant_membership(self):
        db = object_session(self)
        if db is None or "access_scope" not in db.info:
            return None  # Legacy maintenance/test sessions are explicitly unscoped.
        if db.info["access_scope"] != "tenant":
            return None
        org_id = db.info["organization_id"]
        return next((m for m in self.memberships if m.organization_id == org_id), None)
    @property
    def roles(self):
        db = object_session(self)
        if db is not None and "access_scope" in db.info:
            membership = self.tenant_membership()
            return membership.roles if membership else []
        return self.legacy_roles
    @roles.setter
    def roles(self, value):
        membership = self.tenant_membership()
        if membership is not None:
            membership.roles = value
        else:
            self.legacy_roles = value
    @hybrid_property
    def is_active(self):
        membership = self.tenant_membership()
        return self.identity_active and (membership is None or membership.state == "active")
    @is_active.setter
    def is_active(self, value):
        membership = self.tenant_membership()
        if membership is not None:
            membership.state = "active" if value else "suspended"
        else:
            self.identity_active = value
    @is_active.expression
    def is_active(cls):
        return cls.identity_active
    @property
    def denied_permissions(self):
        db = object_session(self)
        if db is not None and "access_scope" in db.info:
            membership = self.tenant_membership()
            return membership.denied_permissions if membership else []
        return self.legacy_denied_permissions
    @denied_permissions.setter
    def denied_permissions(self, value):
        membership = self.tenant_membership()
        if membership is not None:
            membership.denied_permissions = value
        else:
            self.legacy_denied_permissions = value
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="legacy_roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")
class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")
