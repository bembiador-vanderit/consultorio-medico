from io import BytesIO

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.clinical_patient_document import DocumentCreate, DocumentLink, DocumentResponse, DocumentTransition, DocumentUpdate
from app.services import clinical_patient_documents as documents
from app.services.clinical_patient_document_pdf import build_document_pdf
from app.services.clinical_form_pdf import build_form_pdf


router = APIRouter(prefix="/clinical-documents", tags=["Documentos clínicos del paciente"])


@router.get("/patients/{patient_id}", response_model=list[DocumentResponse])
def list_patient_documents(patient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return documents.list_for_patient(db, user, patient_id)


@router.post("/{kind}", response_model=DocumentResponse)
def create_document(kind: str, payload: DocumentCreate, response: Response,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    row, created = documents.create(db, user, kind, payload)
    response.status_code = 201 if created else 200
    return documents.serialize(db, user, kind, row)


@router.get("/{kind}/{document_id}", response_model=DocumentResponse)
def get_document(kind: str, document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return documents.get(db, user, kind, document_id)


@router.put("/{kind}/{document_id}", response_model=DocumentResponse)
def update_document(kind: str, document_id: int, payload: DocumentUpdate,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    return documents.update(db, user, kind, document_id, payload)


@router.post("/{kind}/{document_id}/link-context", response_model=DocumentResponse)
def link_document_context(kind: str, document_id: int, payload: DocumentLink,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    return documents.link_context(db, user, kind, document_id, payload)


@router.post("/{kind}/{document_id}/{action}", response_model=DocumentResponse)
def transition_document(kind: str, document_id: int, action: str, payload: DocumentTransition,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    return documents.transition(db, user, kind, document_id, action, payload)


@router.get("/{kind}/{document_id}/pdf")
def print_document(kind: str, document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    document = documents.get_for_print(db, user, kind, document_id)
    content = (build_form_pdf(document["template_definition"], values=document["values"] or {},
                              profile=document["patient_profile"] or {},
                              document_date=str(document["document_date"]), status=document["status"],
                              signed_at=document["signed_at"])
               if document["template_definition"] else build_document_pdf(document))
    return StreamingResponse(BytesIO(content), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="documento-clinico-{document_id}.pdf"'})
