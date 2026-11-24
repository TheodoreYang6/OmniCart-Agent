"""Alipay website checkout and server-side verification for report payments."""

from base64 import b64decode, b64encode
from datetime import datetime
from functools import lru_cache
import json
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings
from app.models.report_order import ReportOrderModel
from app.services.shopping_report import REPORT_TITLE

_GATEWAYS = {
    "sandbox": "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
    "production": "https://openapi.alipay.com/gateway.do",
}
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _signing_text(values: dict[str, str]) -> bytes:
    return "&".join(f"{key}={value}" for key, value in sorted(values.items()) if value).encode("utf-8")


def _verified_json_field(raw: str, key: str, public_key: rsa.RSAPublicKey) -> dict:
    """Verify the original response bytes before consuming any trade state."""
    decoder = json.JSONDecoder()
    remaining = raw.lstrip()
    if not remaining.startswith("{"):
        raise ValueError("Invalid Alipay envelope")
    remaining = remaining[1:].lstrip()
    values = {}
    payload = ""
    while not remaining.startswith("}"):
        name, end = decoder.raw_decode(remaining)
        rest = remaining[end:].lstrip()
        if not isinstance(name, str) or name in values or not rest.startswith(":"):
            raise ValueError("Invalid Alipay response field")
        value_source = rest[1:].lstrip()
        value, end = decoder.raw_decode(value_source)
        values[name] = value
        if name == key:
            payload = value_source[:end]
        remaining = value_source[end:].lstrip()
        if not remaining.startswith(","):
            break
        remaining = remaining[1:].lstrip()
        if remaining.startswith("}"):
            raise ValueError("Invalid Alipay response delimiter")
    if remaining != "}" or not isinstance(values.get(key), dict) or not isinstance(values.get("sign"), str):
        raise ValueError("Missing Alipay response signature")
    public_key.verify(b64decode(values["sign"], validate=True), payload.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return values[key]


class AlipayReportGateway:
    def __init__(self, mode: str):
        self.endpoint = _GATEWAYS[mode]
        self.app_id = settings.alipay_app_id
        self.seller_id = settings.alipay_seller_id
        self.origin = settings.alipay_web_origin.rstrip("/")
        self.notify_url = settings.alipay_notify_url
        origin = urlsplit(self.origin)
        notify = urlsplit(self.notify_url)
        if not self.app_id.isascii() or not self.app_id.isdecimal():
            raise ValueError("ALIPAY_APP_ID must be a numeric app ID")
        if not self.seller_id.isascii() or not self.seller_id.isdecimal():
            raise ValueError("ALIPAY_SELLER_ID must be the numeric merchant PID")
        sandbox_local = mode == "sandbox" and origin.scheme == "http" and origin.hostname in {"127.0.0.1", "localhost"}
        if (not origin.hostname or origin.path or origin.query or origin.fragment or origin.username
                or not (origin.scheme == "https" or sandbox_local)):
            raise ValueError("ALIPAY_WEB_ORIGIN must be the Web origin")
        if mode == "production" or self.notify_url:
            if (notify.scheme != "https" or not notify.hostname or notify.username or notify.query or notify.fragment
                    or notify.path != "/api/report-payments/alipay/notify"):
                raise ValueError("ALIPAY_NOTIFY_URL must be the HTTPS payment notification endpoint")
        if not settings.alipay_private_key_path or not settings.alipay_public_key_path:
            raise ValueError("Missing Alipay key files")
        private_key = serialization.load_pem_private_key(settings.alipay_private_key_path.read_bytes(), password=None)
        public_key = serialization.load_pem_public_key(settings.alipay_public_key_path.read_bytes())
        if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 2048:
            raise ValueError("Expected a 2048-bit or larger RSA merchant private key")
        if not isinstance(public_key, rsa.RSAPublicKey) or public_key.key_size < 2048:
            raise ValueError("Expected a 2048-bit or larger Alipay RSA public key")
        if private_key.public_key().public_numbers() == public_key.public_numbers():
            raise ValueError("Use the Alipay verification key, not the merchant application public key")
        self._private_key = private_key
        self._public_key = public_key

    def _parameters(self, method: str, biz: dict, **extra: str) -> dict[str, str]:
        parameters = {
            "app_id": self.app_id,
            "method": method,
            "charset": "utf-8",
            "format": "JSON",
            "sign_type": "RSA2",
            "timestamp": datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
            **{key: value for key, value in extra.items() if value},
        }
        signature = self._private_key.sign(_signing_text(parameters), padding.PKCS1v15(), hashes.SHA256())
        return {**parameters, "sign": b64encode(signature).decode("ascii")}

    def checkout_url(self, order: ReportOrderModel) -> str:
        is_cart = order.kind == "cart"
        result_path = f"/cart?payment={order.order_id}" if is_cart else f"/reports?order={order.order_id}"
        params = self._parameters(
            "alipay.trade.page.pay",
            {
                "out_trade_no": order.order_id,
                "total_amount": f"{order.amount_fen // 100}.{order.amount_fen % 100:02}",
                "subject": "欧米购物车订单" if is_cart else REPORT_TITLE,
                "product_code": "FAST_INSTANT_TRADE_PAY",
                "time_expire": order.expires_at.astimezone(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"),
            },
            notify_url=self.notify_url,
            return_url=f"{self.origin}{result_path}&return=alipay",
        )
        return f"{self.endpoint}?{urlencode(params)}"

    def verify_notification(self, fields: dict[str, str]) -> bool:
        if fields.get("sign_type") != "RSA2":
            return False
        data = {key: value for key, value in fields.items() if key not in {"sign", "sign_type"}}
        try:
            self._public_key.verify(
                b64decode(fields.get("sign", ""), validate=True),
                _signing_text(data),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (ValueError, InvalidSignature):
            return False
        return True

    async def query(self, order_id: str) -> dict:
        return await self._dispatch("alipay.trade.query", {"out_trade_no": order_id})

    async def close(self, order_id: str) -> dict:
        return await self._dispatch("alipay.trade.close", {"out_trade_no": order_id})

    async def query_refund(self, trade_no: str, request_no: str) -> dict:
        return await self._dispatch("alipay.trade.fastpay.refund.query", {
            "trade_no": trade_no, "out_request_no": request_no,
        })

    async def _dispatch(self, method: str, fields: dict) -> dict:
        params = self._parameters(method, fields)
        business = {"biz_content": params.pop("biz_content")}
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(self.endpoint, params=params, data=business)
            response.raise_for_status()
        try:
            return _verified_json_field(response.text.strip(), method.replace(".", "_") + "_response", self._public_key)
        except (ValueError, InvalidSignature) as exc:
            raise ValueError("Alipay query response could not be verified") from exc


@lru_cache(maxsize=2)
def get_alipay_report_gateway(mode: str) -> AlipayReportGateway:
    return AlipayReportGateway(mode)
