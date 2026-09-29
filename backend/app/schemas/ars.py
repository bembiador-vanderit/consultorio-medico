from datetime import date
from typing import Literal
from pydantic import Field
from app.schemas.finance import Input, Money, PositiveMoney, Reason


class NewClaim(Input):
    appointment_id: int
    coverage_revision: int = Field(ge=1)


class Transition(Input):
    state: Literal['pending', 'sent', 'received', 'resent', 'cancelled']
    note: Reason | None = None


class Glosa(Input):
    kind: Literal['glosed', 'rejected']
    amount: PositiveMoney
    code: str | None = Field(default=None, max_length=50)
    note: Reason
    approved_amount: Money | None = None


class Correction(Input):
    approved_amount: Money
    note: Reason


class RemittanceInput(Input):
    insurance_company_id: int
    center_id: int | None = None
    received_on: date
    reference: str = Field(min_length=1, max_length=100)
    amount: PositiveMoney


class Allocation(Input):
    claim_id: int
    amount: PositiveMoney


class ApplyInput(Input):
    allocations: list[Allocation] = Field(min_length=1, max_length=100)


class ReverseInput(Input):
    reason: Reason
