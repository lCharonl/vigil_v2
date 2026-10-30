"""Vigil: consomme le flux certstream (lite) et affiche une ligne par domaine."""

import asyncio
import json
import os

import websockets

CERTSTREAM_URL = os.environ.get("CERTSTREAM_URL", "ws://localhost:8080/")
RECONNECT_DELAY = 5


def handle_domain(domain: str, issuer: str, serial: str, is_precert: bool) -> None:
    """Point d'entrée des futures heuristiques."""
    cert_type = "PRECERT" if is_precert else "X509"
    print(f"[{cert_type}]\t{issuer}\t{serial}\t{domain}", flush=True)


async def consume() -> None:
    async with websockets.connect(CERTSTREAM_URL) as ws:
        print(f"[+] Connecté à {CERTSTREAM_URL}", flush=True)
        
        async for raw in ws:
            try:
                msg = json.loads(raw)
                
                if msg.get("message_type") != "certificate_update":
                    continue
                    
                data = msg.get("data", {})
                leaf = data.get("leaf_cert", {})
                
                if leaf.get("is_ca"):
                    continue
                
                update_type = data.get("update_type")
                is_precert = update_type == "PrecertLogEntry"
                serial = leaf.get("serial_number", "?")
                
                issuer_info = leaf.get("issuer", {})
                issuer = issuer_info.get("O") or issuer_info.get("CN") or "?"
                
                for domain in leaf.get("all_domains", []):
                    if domain.startswith("*."):
                        domain = domain[2:]
                        
                    handle_domain(domain, issuer, serial, is_precert)
                    
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"[!] Erreur de parsing : {e}")


async def main() -> None:
    while True:
        try:
            await consume()
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"[!] Connexion perdue ({e}), nouvelle tentative dans {RECONNECT_DELAY}s", flush=True)
            await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[+] Arrêt de Vigil.")