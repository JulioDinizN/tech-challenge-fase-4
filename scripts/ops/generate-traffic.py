#!/usr/bin/env python3
"""Gera tráfego contínuo para popular métricas, logs, traces e o Service Map.

Cria uma flag e uma regra de demonstração (se ainda não existirem) e depois chama
evaluation, flag e targeting em ciclo. As chamadas diretas a flag e targeting
garantem tráfego no auth-service, já que o evaluation usa cache de 30 segundos.
"""

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request


def request(method, url, api_key=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        # URLs fornecidas pelo operador, restritas a http(s) em parse_args.
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-url", default=os.getenv("EVALUATION_URL", "http://localhost:8004"))
    parser.add_argument("--flag-url", default=os.getenv("FLAG_URL", "http://localhost:8002"))
    parser.add_argument("--targeting-url", default=os.getenv("TARGETING_URL", "http://localhost:8003"))
    parser.add_argument("--api-key", default=os.getenv("SERVICE_API_KEY", "tm_key_local_development_only"))
    parser.add_argument("--flag", default="demo-flag")
    parser.add_argument("--rate", type=float, default=5.0, help="ciclos por segundo")
    parser.add_argument("--duration", type=int, default=0, help="segundos; 0 roda até Ctrl+C")
    args = parser.parse_args()
    for url in (args.evaluation_url, args.flag_url, args.targeting_url):
        if not url.startswith(("http://", "https://")):
            parser.error(f"URL inválida: {url}")
    return args


def main():
    args = parse_args()
    flag_status = request("POST", f"{args.flag_url}/flags", args.api_key,
                          {"name": args.flag, "description": "Flag de demonstração", "is_enabled": True})
    rule_status = request("POST", f"{args.targeting_url}/rules", args.api_key,
                          {"flag_name": args.flag, "rules": {"type": "PERCENTAGE", "value": 50}})
    print(f"flag de demonstração: {flag_status}; regra: {rule_status} (409 = já existia)")

    started = time.monotonic()
    counts = {}
    try:
        while not args.duration or time.monotonic() - started < args.duration:
            user = f"user-{random.randint(1, 500)}"  # nosec B311 - apenas variação de carga
            for status in (
                request("GET", f"{args.evaluation_url}/evaluate?user_id={user}&flag_name={args.flag}"),
                request("GET", f"{args.flag_url}/flags/{args.flag}", args.api_key),
                request("GET", f"{args.targeting_url}/rules/{args.flag}", args.api_key),
            ):
                counts[status] = counts.get(status, 0) + 1
            if sum(counts.values()) % 150 == 0:
                print("status HTTP:", dict(sorted(counts.items())), flush=True)
            time.sleep(1 / args.rate)
    except KeyboardInterrupt:
        pass
    print("total por status HTTP:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
