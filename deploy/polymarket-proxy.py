#!/usr/bin/env python3
"""Gera a credencial PROXY do Polymarket Perps. Rode no SEU computador, nunca na VM, e nunca cole a chave no chat.

    pip install "eth-account>=0.13,<1" requests
    python deploy/polymarket-proxy.py saida.json [--days 7]

Pede a chave privada da carteira da conta (digitacao oculta) so para assinar UMA autorizacao EIP-712 `CreateProxy`;
a chave dona NAO e gravada nem enviada. O arquivo de saida guarda apenas o proxy (endereco, chave, segredo, validade).
Leve esse arquivo para a VM (fora dos EUA) com `scp`, modo 600, dono quant, e aponte
POLYMARKET_CREDENTIALS_PATH para ele.
Renove antes de expirar: rode de novo e troque o arquivo. Para revogar, use o app/API do Polymarket.
"""
import argparse
import getpass
import json
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from eth_account import Account

BASE = "https://api.perpetuals.polymarket.com"
DOMAIN = [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
          {"name": "chainId", "type": "uint256"}]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--label", default="quant")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"{a.out} ja existe; escolha outro nome (nao sobrescrevo credenciais)")

    owner = Account.from_key(getpass.getpass("chave privada da carteira da conta (oculta): ").strip())
    proxy = Account.create()
    exp_ms = int((time.time() + a.days * 86400) * 1000)
    salt, ts = secrets.randbits(32), int(time.time() * 1000)
    typed = {"types": {"EIP712Domain": DOMAIN,
                       "CreateProxy": [{"name": "addr", "type": "address"}, {"name": "exp", "type": "uint64"},
                                       {"name": "salt", "type": "uint64"}, {"name": "ts", "type": "uint64"}]},
             "primaryType": "CreateProxy", "domain": {"name": "Polymarket", "version": "1", "chainId": 137},
             "message": {"addr": proxy.address, "exp": exp_ms, "salt": salt, "ts": ts}}
    sig = "0x" + bytes(owner.sign_typed_data(full_message=typed).signature).hex()
    body = {"op": {"type": "createProxy", "args": {"owner": owner.address, "proxy": proxy.address, "expiry": exp_ms}},
            "sig": sig, "salt": salt, "ts": ts, "label": a.label}
    r = requests.post(f"{BASE}/v1/account/proxy", json=body, timeout=20)
    if r.status_code >= 400:
        sys.exit(f"recusado (HTTP {r.status_code}): {r.text[:300]}")
    creds = {"proxy": proxy.address, "private_key": "0x" + bytes(proxy.key).hex(), "secret": r.json()["secret"],
             "expires_at": (datetime.now(timezone.utc) + timedelta(days=a.days)).isoformat(timespec="seconds")}
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f)
    print(f"ok: proxy {proxy.address} valido ate {creds['expires_at']} -> {a.out}")


if __name__ == "__main__":
    main()
