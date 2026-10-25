from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Method = Literal['cash', 'card', 'transfer', 'check', 'other']
CardProvider = Literal['CARDNET', 'AZUL', 'VISANET']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OpenRegister(Input):
    center_id: int
    opening_amount: Money
    notes: str | None = Field(default=None, max_length=1000)


class CloseRegister(Input):
    counted_cash: Money
    notes: str | None = Field(default=None, max_length=1000)


class Part(Input):
    method: Method
    amount: PositiveMoney
    batch_number: str | None = Field(default=None, max_length=40)
    provider: CardProvider | None = None

    @model_validator(mode='after')
    def card_batch(self):
        if self.method == 'card':
            self.batch_number = (self.batch_number or '').strip()
            if not self.batch_number:
                raise ValueError('Indique el número de lote del voucher para pagos con tarjeta')
            if self.provider is None:
                raise ValueError('Seleccione la prestadora de la tarjeta')
        elif self.batch_number is not None or self.provider is not None:
            raise ValueError('La prestadora y el lote solo corresponden a pagos con tarjeta')
        return self


class CardProviderUpdate(Input):
    enabled: bool


class CloseCardBatch(Input):
    provider: CardProvider
    batch_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    declared_count: int = Field(ge=0, le=100000)
    declared_amount: Money
    notes: str | None = Field(default=None, max_length=1000)


class ReopenCardBatch(Input):
    reason: Reason


class CorrectCardAssignment(Input):
    provider: CardProvider
    batch_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    reason: Reason


class Payment(Input):
    register_id: int
    request_key: UUID
    parts: list[Part] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def distinct_methods(self):
        if len({p.method for p in self.parts}) != len(self.parts):
            raise ValueError('Combine los importes del mismo método en una sola línea')
        if sum(p.amount for p in self.parts) > Decimal('9999999999.99'):
            raise ValueError('Importe máximo excedido')
        return self


class NewInvoice(Input):
    request_key: UUID
    center_id: int
    patient_id: int
    appointment_id: int | None = None
    coverage_revision: int | None = Field(default=None, ge=0)
    concept: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    base_amount: Money
    payment: Payment | None = None


class Adjustment(Input):
    request_key: UUID
    kind: Literal['adjustment_in', 'adjustment_out']
    amount: PositiveMoney
    reason: Reason


class Reversal(Input):
    request_key: UUID
    register_id: int
    reason: Reason


class VoidInvoice(Input):
    reason: Reason
