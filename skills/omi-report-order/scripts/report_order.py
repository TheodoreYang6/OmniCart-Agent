#!/usr/bin/env python3
"""Agent client for the OmniCart merchant service. Uses the buyer's existing session."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import shutil
import subprocess
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class NoRedirect(HTTPRedirectHandler):
    """Do not forward a buyer's session token to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path: str, *, authenticated: bool = False, body: dict | None = None, method: str = "GET"):
    origin = os.environ.get("OMNICART_REPORT_BASE_URL", "http://127.0.0.1:8006").rstrip("/")
    url = urlsplit(origin)
    local = url.scheme == "http" and url.hostname in {"127.0.0.1", "::1", "localhost"}
    if not url.hostname or url.username is not None or url.path or url.query or url.fragment or (
        url.scheme != "https" and not local
    ):
        raise ValueError("OMNICART_REPORT_BASE_URL must be an HTTPS or loopback origin")

    headers = {"Accept": "application/json"}
    if authenticated:
        token = os.environ.get("OMNICART_REPORT_SESSION_TOKEN")
        if not token:
            raise ValueError("Set OMNICART_REPORT_SESSION_TOKEN using an existing OmniCart buyer session")
        headers["Authorization"] = "Bearer " + token
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode()
    req = Request(origin + "/api/report-payments/" + path, data=payload, headers=headers, method=method)
    with build_opener(NoRedirect).open(req, timeout=15) as response:
        return json.load(response)


def official_payment_link(checkout_url: str, session_id: str, framework: str) -> str:
    url = urlsplit(checkout_url)
    if url.scheme != "https" or url.netloc not in {
        "openapi.alipay.com", "openapi-sandbox.dl.alipaydev.com",
    } or url.path != "/gateway.do":
        raise ValueError("Unexpected Alipay checkout URL")
    binary = shutil.which("alipay-bot")
    if not binary:
        installed = Path.home() / ".local/bin/alipay-bot"
        if not os.access(installed, os.X_OK):
            raise ValueError("Install the official Alipay payment CLI before handing off checkout")
        binary = str(installed)

    # Pass only the signed checkout material to the official CLI. The buyer's
    # OmniCart session token never becomes a CLI argument or relay payload.
    nonce_path = "/" + token_urlsafe(24)
    content = json.dumps({"alipayMetadata": {"orderStr": checkout_url}}).encode()

    class Relay(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != nonce_path:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_):
            pass

    with HTTPServer(("127.0.0.1", 0), Relay) as relay:
        thread = Thread(target=relay.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            env = {key: value for key, value in os.environ.items() if key != "OMNICART_REPORT_SESSION_TOKEN"}
            process = subprocess.run([
                binary, "proxy-trade-request", "http", "--method", "GET",
                "--url", f"http://127.0.0.1:{relay.server_port}{nonce_path}",
                "--extract-path", "$.alipayMetadata.orderStr", "--payload-type", "link",
                "--session-id", session_id, "--framework", framework, "--json",
            ], env=env, capture_output=True, text=True, timeout=15, check=True)
            reply = json.loads(process.stdout)
            link = reply["data"]["alipayMetadata"]["orderStr"]
        except (subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("The official Alipay CLI could not create a payment link") from exc
        finally:
            relay.shutdown()
            thread.join()
    if reply.get("code") != 0 or not isinstance(link, str) or not link.startswith("alipay_"):
        raise ValueError("The official Alipay CLI did not return an Alipay payment link")
    return link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("service")
    commands.add_parser("categories")
    quote = commands.add_parser("quote")
    quote.add_argument("category")
    quote.add_argument("budget_fen", type=int)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("order_id", type=UUID)
    confirm.add_argument("--session-id", help="Session ID used by the official Alipay payment skill")
    confirm.add_argument("--framework", default="codex")
    for name in ("status", "refresh"):
        commands.add_parser(name).add_argument("order_id", type=UUID)
    args = parser.parse_args()
    try:
        if args.command in {"service", "categories"}:
            payload = request(args.command)
        elif args.command == "quote":
            payload = request("orders", authenticated=True, method="POST", body={
                "category": args.category, "budget_fen": args.budget_fen, "channel": "agent",
            })
        else:
            path = "orders/" + args.order_id.hex
            if args.command == "confirm":
                payload = request(path + "/confirm", authenticated=True, method="POST", body={"confirmed": True})
                if payload.get("checkout_url") and args.session_id:
                    payload["paymentLink"] = official_payment_link(
                        payload.pop("checkout_url"), args.session_id, args.framework,
                    )
                elif payload.get("checkout_url") and payload["mode"] == "production":
                    raise ValueError("Provide the Alipay payment skill session ID to hand off the production checkout")
            elif args.command == "refresh":
                payload = request(path + "/refresh", authenticated=True, method="POST")
            else:
                payload = request(path, authenticated=True)
    except HTTPError as exc:
        detail = exc.reason
        try:
            detail = json.load(exc).get("detail", detail)
        except ValueError:
            pass
        parser.exit(1, f"OmniCart HTTP {exc.code}: {detail}\n")
    except (URLError, ValueError) as exc:
        parser.exit(1, f"OmniCart request failed: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
