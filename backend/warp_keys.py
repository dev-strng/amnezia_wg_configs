import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from models import KeyPair, WarpRegisterResponse

WARP_API = "https://api.cloudflareclient.com/v0a2158/reg"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "1.1.1.1/6.30",
    "CF-Client-Version": "a-6.30-3596",
}


def generate_keypair() -> KeyPair:
    """Generate a new WireGuard key pair."""
    private_key = X25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes_raw()
    pub_bytes = private_key.public_key().public_bytes_raw()
    return KeyPair(
        private_key=base64.b64encode(priv_bytes).decode(),
        public_key=base64.b64encode(pub_bytes).decode(),
    )


async def register_warp_account() -> WarpRegisterResponse:
    """
    Register a new Cloudflare WARP account and return credentials.
    This calls the WARP API to get a valid PrivateKey + server PublicKey.
    """
    kp = generate_keypair()
    install_id = uuid.uuid4().hex
    body = {
        "key": kp.public_key,
        "install_id": install_id,
        "fcm_token": f"{install_id}:APA91b{os.urandom(32).hex()}",
        "tos": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "model": "PC",
        "serial_number": str(uuid.uuid4()),
        "locale": "en_US",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(WARP_API, headers=HEADERS, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        content = None
        try:
            content = await e.response.aread()
        except Exception:
            content = e.response.text if hasattr(e.response, 'text') else None
        raise ValueError(f"WARP API returned status {e.response.status_code}: {e.response.text}, content: {content}") from e
    except httpx.RequestError as e:
        raise ValueError(f"Error connecting to WARP API: {repr(e)}") from e
    except json.JSONDecodeError:
        raise ValueError(f"WARP API returned non-JSON response: {resp.text}") from e
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise ValueError(f"An unexpected error occurred while fetching from WARP API: {e}\nTraceback: {tb}") from e

    # Now parse the JSON data more robustly
    config = data.get("config", {})
    if not isinstance(config, dict):
        raise ValueError("WARP API response 'config' is not a dictionary.")

    peers = config.get("peers", [])
    if not isinstance(peers, list) or len(peers) == 0:
        raise ValueError("WARP API response did not contain any valid peer information.")

    peer_info = peers[0]
    if not isinstance(peer_info, dict):
        raise ValueError("First peer in WARP API response is not a dictionary.")

    peer_pub_key = peer_info.get("public_key")
    if not peer_pub_key or not isinstance(peer_pub_key, str):
        raise ValueError("WARP API response for peer does not contain a valid string 'public_key'.")

    endpoint_data = peer_info.get("endpoint", {})
    if not isinstance(endpoint_data, dict):
        default_endpoint = "162.159.193.1:2408" # Fallback endpoint
    else:
        default_endpoint = endpoint_data.get("v4", "162.159.193.1:2408")

    iface = config.get("interface", {})
    if not isinstance(iface, dict):
        raise ValueError("WARP API response 'interface' is not a dictionary.")

    addresses = iface.get("addresses", {})
    if not isinstance(addresses, dict):
        raise ValueError("WARP API response 'addresses' is not a dictionary.")

    addr_v4 = addresses.get("v4", "172.16.0.2")
    addr_v6 = addresses.get("v6", "")

    return WarpRegisterResponse(
        private_key=kp.private_key,
        public_key=peer_pub_key,
        address_v4=f"{addr_v4}/32",
        address_v6=f"{addr_v6}/128" if addr_v6 else "",
        account_id=data.get("id", ""),
        token=data.get("token", ""),
        default_endpoint=default_endpoint,
    )
