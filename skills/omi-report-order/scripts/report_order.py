#!/usr/bin/env python3
"""Agent client for the OmniCart merchant service. Uses the buyer's existing session."""

import argparse
import json
import os
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("service")
    commands.add_parser("categories")
    generate = commands.add_parser("generate")
    generate.add_argument("category")
    generate.add_argument("budget_fen", type=int)
    commands.add_parser("status").add_argument("order_id", type=UUID)
    args = parser.parse_args()
    try:
        if args.command in {"service", "categories"}:
            payload = request(args.command)
        elif args.command == "generate":
            payload = request("orders", authenticated=True, method="POST", body={
                "category": args.category, "budget_fen": args.budget_fen, "channel": "agent",
            })
        else:
            payload = request("orders/" + args.order_id.hex, authenticated=True)
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
