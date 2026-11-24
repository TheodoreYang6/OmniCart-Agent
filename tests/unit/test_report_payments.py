"""Regressions for settlement, replay protection and RSA2 verification."""

from base64 import b64encode
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException
import pytest

from app.api.report_payments import _view
from app.services.payment_settlement import _reconcile
from app.core.config import settings
from app.models.report_order import ReportOrderModel
from app.services.alipay_report_gateway import AlipayReportGateway, _signing_text, _verified_json_field


@pytest.fixture
def order():
    now = datetime.now(timezone.utc)
    return ReportOrderModel(
        order_id="a" * 32, user_id="buyer", amount_fen=199, status="pending",
        channel="web", environment="sandbox", app_id="123456789", seller_id="987654321",
        report={"category": "耳机", "budget_fen": 50000, "candidate_count": 2, "products": []},
        created_at=now, expires_at=now + timedelta(minutes=30),
    )


@pytest.fixture(scope="module")
def rsa_pair():
    return (
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )


@pytest.fixture
def gateway(monkeypatch, tmp_path, rsa_pair, order):
    merchant, alipay = rsa_pair
    private_path = tmp_path / "merchant.pem"
    public_path = tmp_path / "alipay.pem"
    private_path.write_bytes(merchant.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    public_path.write_bytes(alipay.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    for name, value in {
        "alipay_app_id": order.app_id,
        "alipay_seller_id": order.seller_id,
        "alipay_private_key_path": private_path,
        "alipay_public_key_path": public_path,
        "alipay_web_origin": "http://127.0.0.1:5173",
    }.items():
        monkeypatch.setattr(settings, name, value)
    return AlipayReportGateway("sandbox")


def paid_trade(order):
    return {
        "out_trade_no": order.order_id, "seller_id": order.seller_id,
        "total_amount": "1.99", "trade_status": "TRADE_SUCCESS", "trade_no": "provider-trade",
    }


def sign(key, data: bytes):
    return b64encode(key.sign(data, padding.PKCS1v15(), hashes.SHA256())).decode("ascii")


def test_checkout_signs_the_frozen_amount_and_order(gateway, rsa_pair, order):
    url = urlsplit(gateway.checkout_url(order))
    fields = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert url.hostname == "openapi-sandbox.dl.alipaydev.com"
    assert fields["method"] == "alipay.trade.page.pay"
    assert parse_qs(urlsplit(fields["return_url"]).query) == {"order": [order.order_id], "return": ["alipay"]}
    biz = json.loads(fields["biz_content"])
    assert (biz["out_trade_no"], biz["total_amount"]) == (order.order_id, "1.99")
    assert fields.pop("sign") == sign(rsa_pair[0], _signing_text(fields))


def test_callback_requires_rsa2_and_rejects_tampering(gateway, rsa_pair, order):
    fields = {**paid_trade(order), "app_id": order.app_id}
    fields.update(sign=sign(rsa_pair[1], _signing_text(fields)), sign_type="RSA2")
    assert gateway.verify_notification(fields)
    assert not gateway.verify_notification({**fields, "total_amount": "0.01"})
    assert not gateway.verify_notification({**fields, "sign_type": "RSA"})
    assert not gateway.verify_notification({**fields, "sign": "?"})


def test_query_verifies_exact_wire_payload(rsa_pair):
    body = '{"code": "10000", "trade_status": "TRADE_SUCCESS"}'
    signature = sign(rsa_pair[1], body.encode())
    envelope = '{"sign":"' + signature + '","alipay_trade_query_response": ' + body + '}'
    key = rsa_pair[1].public_key()
    assert _verified_json_field(envelope, "alipay_trade_query_response", key)["code"] == "10000"
    with pytest.raises(InvalidSignature):
        _verified_json_field(envelope.replace("10000", "10001"), "alipay_trade_query_response", key)


@pytest.mark.parametrize("field,new_value", [
    ("total_amount", "0.01"), ("seller_id", "other"), ("out_trade_no", "wrong"), ("trade_no", ""),
])
def test_reconciliation_rejects_mismatched_trade(order, field, new_value):
    with pytest.raises(HTTPException, match="409"):
        _reconcile(order, {**paid_trade(order), field: new_value})
    assert _view(order)["report"] is None


def test_replay_preserves_one_receipt_and_report(order):
    assert _view(order)["report"] is None
    trade = paid_trade(order)
    _reconcile(order, trade)
    paid_at = order.paid_at
    _reconcile(order, trade)
    assert order.paid_at == paid_at
    assert _view(order)["report"] == order.report
    with pytest.raises(HTTPException, match="409"):
        _reconcile(order, {**trade, "trade_no": "different-trade"})
