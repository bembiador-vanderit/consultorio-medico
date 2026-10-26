"""Synthetic document contracts; never writes to the official 0065 database."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import document_designer
from app.models import Permission, Role, User
from app.models.document_template import DocumentTemplate, DocumentTemplateVersion, DocumentTemplateAudit
from app.models.finance import CashMovement, Invoice, CashRegister
from app.services.document_designer import DEFAULT_DEFINITION, effective
from app.services.document_pdf import render_financial_pdf, sample_data
from test_finance_6c6 import financial_api, open_cash, bill, payment, post
from test_insurance_6c5 import insurance_api
from test_organization_isolation import tenant_api


def test_sample_renderer_color_bw_and_three_types():
    for kind in ("invoice", "receipt", "cash_close"):
        color = render_financial_pdf(kind, sample_data(kind), DEFAULT_DEFINITION)
        bw = render_financial_pdf(kind, sample_data(kind), {**DEFAULT_DEFINITION, "print_mode": "bw"})
        assert color.startswith(b"%PDF") and bw.startswith(b"%PDF")
        assert color != bw and len(color) > 1200


def test_financial_pdf_reprint_does_not_mutate_money(financial_api):
    client, headers, engine, data = financial_api
    client.app.include_router(document_designer.router, prefix="/api/v1")
    register = open_cash(client, headers, data[1])
    invoice = post(client, headers, "/invoices", bill(data[1], payment=payment(register, ("cash", "200"))))
    movement_id = client.get(f"/api/v1/finance/invoices/{invoice['id']}", headers=headers).json()["movements"][0]["id"]
    with Session(engine) as db:
        before = (db.get(Invoice, invoice["id"]).paid_amount, db.scalar(select(func.count(CashMovement.id))),
                  db.get(CashRegister, register["id"]).state)
    for kind, record_id in (("invoice", invoice["id"]), ("receipt", movement_id)):
        response = client.get(f"/api/v1/documents/finance/{kind}/{record_id}/pdf", headers=headers)
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"%PDF")
        retry = client.get(f"/api/v1/documents/finance/{kind}/{record_id}/pdf?action=reprint", headers=headers)
        assert retry.status_code == 200 and retry.content.startswith(b"%PDF")
    closed = post(client, headers, f"/registers/{register['id']}/close", {"counted_cash": "300"}, 200)
    pdf = client.get(f"/api/v1/documents/finance/cash_close/{register['id']}/pdf", headers=headers)
    assert closed["difference"] == "0.00" and pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    with Session(engine) as db:
        assert (db.get(Invoice, invoice["id"]).paid_amount, db.scalar(select(func.count(CashMovement.id)))) == before[:2]
        assert db.scalar(select(func.count(DocumentTemplateAudit.id)).where(DocumentTemplateAudit.action == "pdf_reprint")) == 2
    assert client.get(f"/api/v1/documents/finance/invoice/{invoice['id']}/pdf?action=download", headers=headers).headers["content-disposition"].startswith("attachment")


def test_template_versions_tenant_and_permissions(financial_api):
    client, headers, engine, data = financial_api
    client.app.include_router(document_designer.router, prefix="/api/v1")
    body = {"document_type": "invoice", "name": "Factura de prueba", "center_id": data[1]["center"],
            "definition": {**DEFAULT_DEFINITION, "print_mode": "bw"}}
    assert client.get("/api/v1/documents/effective/invoice", headers=headers).json()["source"] == "atlas_default"
    assert client.post("/api/v1/documents/drafts", headers=headers, json={**body, "center_id": data[2]["center"]}).status_code == 404
    created = client.post("/api/v1/documents/drafts", headers=headers, json=body)
    assert created.status_code == 200, created.text
    ids = created.json()
    assert client.get(f"/api/v1/documents/effective/invoice?center_id={data[1]['center']}", headers=headers).json()["source"] == "atlas_default"
    published = client.post(f"/api/v1/documents/templates/{ids['template_id']}/versions/{ids['version_id']}/publish", headers=headers)
    assert published.status_code == 200, published.text
    actual = client.get(f"/api/v1/documents/effective/invoice?center_id={data[1]['center']}", headers=headers).json()
    assert actual["definition"]["print_mode"] == "bw" and actual["version"] == 1
    assert client.post(f"/api/v1/documents/templates/{ids['template_id']}/versions/{ids['version_id']}/publish", headers=headers).status_code == 409
    body["definition"]["margin_mm"] = 20
    next_ = client.post("/api/v1/documents/drafts", headers=headers, json=body).json()
    assert next_["version"] == 2
    with Session(engine) as db:
        count = db.scalar(select(func.count(DocumentTemplateAudit.id)))
    same = client.post("/api/v1/documents/drafts", headers=headers, json=body)
    assert same.status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count(DocumentTemplateAudit.id))) == count
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        admin.permissions = [p for p in admin.permissions if p.code != "documents:publish"]
        db.commit()
    assert client.post(f"/api/v1/documents/templates/{ids['template_id']}/versions/{next_['version_id']}/publish", headers=headers).status_code == 403
    with Session(engine) as db:
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        admin.permissions = [p for p in admin.permissions if p.code != "finance:read"]
        db.commit()
    assert client.get("/api/v1/documents/finance/invoice/1/pdf", headers=headers).status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(func.count(DocumentTemplate.id))) == 1
        assert db.scalar(select(func.count(DocumentTemplateVersion.id))) == 2


def test_cash_close_requires_closed_register_and_cross_tenant_pdf_denied(financial_api):
    client, headers, engine, data = financial_api
    client.app.include_router(document_designer.router, prefix="/api/v1")
    register = open_cash(client, headers, data[1])
    assert client.get(f"/api/v1/documents/finance/cash_close/{register['id']}/pdf", headers=headers).status_code == 409
    with Session(engine) as db:
        other = CashRegister(organization_id=2, center_id=data[2]["center"], opened_by=register["opened_by"], opening_amount=0)
        db.add(other); db.commit(); other_id = other.id
    assert client.get(f"/api/v1/documents/finance/cash_close/{other_id}/pdf", headers=headers).status_code == 404


def test_pdf_financial_values_match_source_records_with_mixed_payment(financial_api):
    client, headers, engine, data = financial_api
    client.app.include_router(document_designer.router, prefix="/api/v1")
    register = open_cash(client, headers, data[1])
    invoice = post(client, headers, "/invoices", bill(data[1], payment=payment(register, ("cash", "200"), ("card", "300"))))
    movement_id = client.get(f"/api/v1/finance/invoices/{invoice['id']}", headers=headers).json()["movements"][0]["id"]
    with Session(engine) as db:
        row = db.get(Invoice, invoice["id"])
        movement = db.get(CashMovement, movement_id)
        rendered_invoice = document_designer._invoice_data(db, row)
        rendered_receipt = document_designer._receipt_data(db, db.get(User, movement.created_by), movement)
        assert rendered_invoice["totals"] == [
            ("Total", "DOP 1,500.00"), ("Parte ARS", "DOP 0.00"),
            ("Parte paciente", "DOP 1,500.00"),
            ("Pagado neto por paciente", "DOP 500.00"),
            ("Saldo paciente", "DOP 1,000.00"),
        ]
        assert rendered_receipt["totals"] == [
            ("Monto recibido", "DOP 500.00"),
            ("Saldo posterior a este cobro", "DOP 1,000.00"),
        ]
        assert "Efectivo DOP 200.00" in rendered_receipt["details"][0][1]
        assert "CARDNET lote QA-LOTE-001" in rendered_receipt["details"][0][1]
    post(client, headers, f"/registers/{register['id']}/card-batches", {
        "provider": "CARDNET", "batch_number": "QA-LOTE-001",
        "declared_count": 1, "declared_amount": "300",
    })
    closed = post(client, headers, f"/registers/{register['id']}/close", {"counted_cash": "300"}, 200)
    with Session(engine) as db:
        totals = document_designer._close_data(db, db.get(CashRegister, register["id"]))["totals"]
        assert ("Efectivo esperado", "DOP 300.00") in totals
        assert ("Efectivo contado", "DOP 300.00") in totals
        assert ("Diferencia", "DOP 0.00") in totals
        assert closed["difference"] == "0.00"
