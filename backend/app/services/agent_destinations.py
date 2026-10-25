"""Read-only availability, NOT permission to execute or retrieve a document."""
from sqlalchemy import select
from app.models import CareCenter
from app.models.local_agent import LocalAgent, AgentPrinter, AgentWorkgroup
from app.services.appointment_scope import assigned_center_ids, is_role
from app.services import local_agents as registry


def destinations(db, user, *, center_id=None, workgroup_id=None, paper_name=None, origin_type="WEB_DESKTOP"):
    registry.ensure_scope(db)
    centers = set(db.scalars(select(CareCenter.id).where(CareCenter.is_active.is_(True))))
    if not is_role(user, "admin"):
        centers &= assigned_center_ids(user)
    if center_id is not None:
        centers &= {center_id}
    rows = []
    for agent in db.scalars(select(LocalAgent).where(LocalAgent.center_id.in_(centers)).order_by(LocalAgent.id)):
        if registry.state(agent) != "online" or (workgroup_id is not None and agent.workgroup_id != workgroup_id):
            continue
        group = db.scalar(select(AgentWorkgroup).where(AgentWorkgroup.id == agent.workgroup_id,
                                                     AgentWorkgroup.center_id == agent.center_id))
        if group is None:
            continue
        for printer in db.scalars(select(AgentPrinter).where(AgentPrinter.agent_id == agent.id, AgentPrinter.available.is_(True))):
            if paper_name and not any(p.get("name", "").casefold() == paper_name.casefold() for p in printer.papers):
                continue
            rows.append({"target_agent": agent.agent_uuid, "target_printer": printer.local_id,
                         "station_name": agent.station_name, "printer_name": printer.display_name,
                         "center_id": agent.center_id, "workgroup_id": group.id,
                         "route": "ATLAS_HTTPS", "lan_channel_available": False,
                         "execution_enabled": False, "document_authorization_required": True})
    return {"origin_type": origin_type, "origin_user": user.id, "source_agent_required": False,
            "availability_only": True, "execution_enabled": False, "destinations": rows}
