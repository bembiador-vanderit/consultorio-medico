from pydantic import BaseModel, EmailStr, Field


class EmailSendRequest(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


class WhatsAppSendRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    message: str = Field(min_length=1, max_length=4096)


class CommunicationResponse(BaseModel):
    channel: str
    status: str
    detail: str
    action_url: str | None = None
