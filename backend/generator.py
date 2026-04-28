from models import ConfigRequest, ConfigResponse


def generate_awg_config(req: ConfigRequest) -> ConfigResponse:
    """Generate an AmneziaWG 2.0 .conf file from the request parameters."""

    config = f"""\
[Interface]
PrivateKey = {req.private_key}
Address = {req.address}
DNS = {req.dns}
MTU = {req.mtu}
Jc = {req.jc}
Jmin = {req.jmin}
Jmax = {req.jmax}
S1 = {req.s1}
S2 = {req.s2}
H1 = {req.h1}
H2 = {req.h2}
H3 = {req.h3}
H4 = {req.h4}

[Peer]
PublicKey = {req.peer_public_key}
AllowedIPs = {req.allowed_ips}
Endpoint = {req.peer_endpoint}
PersistentKeepalive = {req.persistent_keepalive}
"""

    # Derive a safe filename from the endpoint
    safe_ep = req.peer_endpoint.replace(":", "_").replace(".", "-")
    filename = f"amnezia_wg_{safe_ep}.conf"

    return ConfigResponse(config=config, filename=filename)


def get_recommended_awg_params() -> dict:
    """Return recommended AmneziaWG 2.0 obfuscation parameters."""
    return {
        "jc": 4,
        "jmin": 40,
        "jmax": 70,
        "s1": 0,
        "s2": 0,
        "h1": 1,
        "h2": 2,
        "h3": 3,
        "h4": 4,
        "mtu": 1280,
        "persistent_keepalive": 25,
        "dns": "1.1.1.1, 1.0.0.1",
        "allowed_ips": "0.0.0.0/0, ::/0",
    }
