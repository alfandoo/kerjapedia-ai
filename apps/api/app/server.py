"""Container entrypoint with explicit proxy trust."""

from __future__ import annotations

import os
from ipaddress import ip_network

import uvicorn


def trusted_proxy_ips(value: str) -> list[str]:
    hosts = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            network = ip_network(item, strict=True)
        except ValueError as exc:
            raise ValueError(
                "FORWARDED_ALLOW_IPS must contain explicit proxy IPs or CIDRs."
            ) from exc
        if network.prefixlen == 0:
            raise ValueError("FORWARDED_ALLOW_IPS must not trust every address.")
        hosts.append(item)
    return hosts


def main() -> None:
    hosts = trusted_proxy_ips(os.environ.get("FORWARDED_ALLOW_IPS", ""))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=bool(hosts),
        forwarded_allow_ips=hosts,
    )


if __name__ == "__main__":
    main()
