"""Run only on disposable finance_concurrency_test PostgreSQL."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.models import CareCenter, User, Role, Patient
from app.models.finance import CashMovement, Invoice
from app.schemas.finance import OpenRegister, CloseRegister, NewInvoice, Payment
from app.services import finance
from app.services.bootstrap import seed_identity


@pytest.fixture
def postgres():
    url = os.environ.get('FINANCE_POSTGRES_URL')
    if not url:
        pytest.skip('Requires disposable finance_concurrency_test PostgreSQL')
    engine = create_engine(url)
    assert engine.url.database == 'finance_concurrency_test'
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        role = db.scalar(select(Role).where(Role.code == 'admin'))
        users = [User(email=f'finance{i}@example.test', full_name='Synthetic', password_hash='unused', roles=[role]) for i in range(2)]
        center = CareCenter(name='Synthetic', city='Test')
        patient = Patient(first_name='Synthetic', last_name='Finance', date_of_birth=date(1990,1,1))
        db.add_all([*users, center, patient]); db.commit()
        uid, uid2, cid, pid = users[0].id, users[1].id, center.id, patient.id
    yield engine, (uid, uid2, cid, pid)
    Base.metadata.drop_all(engine); engine.dispose()


def race(engine, functions):
    barrier = Barrier(2)
    def run(fn):
        with Session(engine) as db:
            barrier.wait(timeout=30)
            try:
                fn(db)
                return 200
            except HTTPException as e:
                db.rollback()
                return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(run, functions))


def setup_payment(engine, ids):
    uid, uid2, cid, pid = ids
    with Session(engine) as db:
        user = db.get(User, uid)
        r1 = finance.open_register(db, user, OpenRegister(center_id=cid, opening_amount='0'))
        r2 = finance.open_register(db, db.get(User, uid2), OpenRegister(center_id=cid, opening_amount='0'))
        invoice = finance.create_invoice(db, user, NewInvoice(request_key=uuid4(), center_id=cid, patient_id=pid, concept='Synthetic', base_amount='100'))
        return r1.id, r2.id, invoice.id


def payload(rid, key=None):
    return Payment(register_id=rid, request_key=key or uuid4(), parts=[{'method':'cash','amount':'100'}])


def test_concurrent_openings_leave_one_register(postgres):
    engine, (uid, _, cid, _) = postgres
    def opening(db):
        finance.open_register(db, db.get(User, uid), OpenRegister(center_id=cid, opening_amount='0'))
    assert sorted(race(engine, [opening, opening])) == [200, 409]


def test_two_cashiers_cannot_overpay_one_invoice(postgres):
    engine, ids = postgres
    r1, r2, iid = setup_payment(engine, ids)
    functions = [lambda db: finance.pay_invoice(db, db.get(User, ids[0]), iid, payload(r1)),
                 lambda db: finance.pay_invoice(db, db.get(User, ids[1]), iid, payload(r2))]
    assert sorted(race(engine, functions)) == [200, 422]
    with Session(engine) as db:
        assert db.get(Invoice, iid).paid_amount == 100
        assert len(db.scalars(select(CashMovement)).all()) == 1


def test_concurrent_retry_has_one_mixed_operation(postgres):
    engine, ids = postgres
    r1, _, iid = setup_payment(engine, ids)
    p = Payment(register_id=r1, request_key=uuid4(), parts=[{'method':'cash','amount':'40'}, {'method':'card','amount':'60'}])
    def pay(db):
        finance.pay_invoice(db, db.get(User, ids[0]), iid, p)
    assert race(engine, [pay, pay]) == [200, 200]
    with Session(engine) as db:
        assert db.get(Invoice, iid).paid_amount == 100
        assert len(db.scalars(select(CashMovement)).all()) == 1


def test_payment_vs_close_keeps_frozen_close_consistent(postgres):
    engine, ids = postgres
    r1, _, iid = setup_payment(engine, ids)
    result = race(engine, [lambda db: finance.pay_invoice(db, db.get(User, ids[0]), iid, payload(r1)),
                          lambda db: finance.close_register(db, db.get(User, ids[0]), r1, CloseRegister(counted_cash='0', notes='Race test'))])
    assert result[1] == 200 and result[0] in (200, 409)
    with Session(engine) as db:
        row = finance.register_access(db, db.get(User, ids[0]), r1)
        assert row.state == 'closed'
        assert row.expected_cash == finance.register_totals(db, row)['expected_cash']
        assert row.expected_cash == db.get(Invoice, iid).paid_amount
