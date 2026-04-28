from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class EndpointStatus(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    CLOSED = "closed"
    ERROR = "error"


class EndpointResult(BaseModel):
    ip: str
    port: int
    latency_ms: Optional[float] = None
    status: EndpointStatus
    error: Optional[str] = None


class ScanRequest(BaseModel):
    ip_ranges: List[str] = Field(default=[
        "162.159.192.0/24",
        "162.159.193.0/24",
        "162.159.195.0/24",
        "188.114.96.0/24",
        "188.114.97.0/24",
    ])
    ports: List[int] = Field(default=[2408])
    count_per_range: int = Field(default=50, ge=1, le=255)
    timeout: float = Field(default=2.0, ge=0.5, le=10.0)


class ScanProgress(BaseModel):
    type: str  # "start" | "result" | "done" | "error"
    completed: int = 0
    total: int = 0
    progress_pct: float = 0.0
    result: Optional[EndpointResult] = None
    message: Optional[str] = None


class ConfigRequest(BaseModel):
    private_key: str
    peer_public_key: str
    peer_endpoint: str
    address: str = "172.16.0.2/32"
    dns: str = "1.1.1.1, 1.0.0.1"
    allowed_ips: str = "0.0.0.0/0, ::/0"
    jc: int = Field(default=4, ge=1, le=128)
    jmin: int = Field(default=40, ge=10, le=1000)
    jmax: int = Field(default=70, ge=10, le=1280)
    s1: int = Field(default=0, ge=0, le=1280)
    s2: int = Field(default=0, ge=0, le=1280)
    h1: int = Field(default=1, ge=1)
    h2: int = Field(default=2, ge=1)
    h3: int = Field(default=3, ge=1)
    h4: int = Field(default=4, ge=1)
    persistent_keepalive: int = Field(default=25, ge=0, le=65535)
    mtu: int = Field(default=1280, ge=576, le=1500)


class ConfigResponse(BaseModel):
    config: str
    filename: str


class WarpRegisterResponse(BaseModel):
    private_key: str
    public_key: str
    address_v4: str
    address_v6: str
    account_id: str
    token: str
    default_endpoint: str


class KeyPair(BaseModel):
    private_key: str
    public_key: str
