"""Amazon EC2: lê os metadados da instância (IMDSv2) para mostrar na tela
qual servidor está respondendo. Fora da AWS retorna None."""
import urllib.request
from functools import lru_cache
from typing import Optional

IMDS = "http://169.254.169.254/latest"


def _get(path: str, token: str) -> str:
    req = urllib.request.Request(f"{IMDS}/{path}", headers={"X-aws-ec2-metadata-token": token})
    with urllib.request.urlopen(req, timeout=1) as resp:
        return resp.read().decode()


@lru_cache(maxsize=1)
def metadata() -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"{IMDS}/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            token = resp.read().decode()
        return {
            "instance_id": _get("meta-data/instance-id", token),
            "instance_type": _get("meta-data/instance-type", token),
            "availability_zone": _get("meta-data/placement/availability-zone", token),
            "private_ip": _get("meta-data/local-ipv4", token),
        }
    except Exception:
        return None
