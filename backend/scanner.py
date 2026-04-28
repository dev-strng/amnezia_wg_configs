import asyncio
import ipaddress
import os
import random
import re
import socket
import time
from typing import List, Optional, Tuple, AsyncIterator

from models import EndpointResult, EndpointStatus, ScanProgress, ScanRequest

DEFAULT_RANGES = [
    "162.159.192.0/24",
    "162.159.193.0/24",
    "162.159.195.0/24",
    "188.114.96.0/24",
    "188.114.97.0/24",
    "188.114.98.0/24",
    "188.114.99.0/24",
]
DEFAULT_PORTS = [2408, 500, 1701, 4500, 8443]


def sample_ips(cidr: str, count: int) -> List[str]:
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = list(net.hosts())
    if len(hosts) <= count:
        return [str(h) for h in hosts]
    return [str(h) for h in random.sample(hosts, count)]


async def ping_host(ip: str, timeout: float = 2.0) -> Optional[float]:
    """Ping host once; return RTT in ms or None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(max(1, int(timeout))), "-q", ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return None

        if proc.returncode != 0:
            return None

        output = stdout.decode()
        match = re.search(
            r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms", output
        )
        if match:
            return float(match.group(1))
        return None
    except Exception:
        return None


async def check_udp_endpoint(
    ip: str, port: int, timeout: float = 2.0
) -> Tuple[bool, Optional[float]]:
    """Send a WG-like UDP packet; return (responded, latency_ms)."""
    loop = asyncio.get_event_loop()
    start = time.monotonic()
    sock: Optional[socket.socket] = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.connect((ip, port))
        packet = bytes([1, 0, 0, 0]) + os.urandom(144)
        await loop.sock_sendall(sock, packet)
        try:
            await asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=timeout)
            latency = (time.monotonic() - start) * 1000
            return True, latency
        except asyncio.TimeoutError:
            return False, None
        except (ConnectionRefusedError, OSError):
            return False, None
    except Exception:
        return False, None
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


async def _check_endpoint(ip: str, port: int, timeout: float) -> EndpointResult:
    """ICMP ping first; fall back to UDP probe."""
    ping_latency = await ping_host(ip, timeout=timeout)
    if ping_latency is not None:
        return EndpointResult(
            ip=ip, port=port,
            latency_ms=round(ping_latency, 2),
            status=EndpointStatus.OK,
        )
    udp_responded, udp_latency = await check_udp_endpoint(ip, port, timeout=timeout)
    if udp_responded and udp_latency is not None:
        return EndpointResult(
            ip=ip, port=port,
            latency_ms=round(udp_latency, 2),
            status=EndpointStatus.OK,
        )
    return EndpointResult(ip=ip, port=port, latency_ms=None, status=EndpointStatus.TIMEOUT)


async def scan_endpoints(request: ScanRequest) -> AsyncIterator[ScanProgress]:
    """Async generator: yields ScanProgress events while scanning."""
    tasks: List[Tuple[str, int]] = []
    for cidr in request.ip_ranges:
        try:
            for ip in sample_ips(cidr, request.count_per_range):
                for port in request.ports:
                    tasks.append((ip, port))
        except ValueError:
            continue

    random.shuffle(tasks)
    total = len(tasks)
    yield ScanProgress(type="start", total=total, completed=0, progress_pct=0.0)

    semaphore = asyncio.Semaphore(100)
    completed = 0
    queue: asyncio.Queue[EndpointResult] = asyncio.Queue()

    async def worker(ip: str, port: int) -> None:
        async with semaphore:
            result = await _check_endpoint(ip, port, timeout=request.timeout)
        await queue.put(result)

    worker_tasks = [asyncio.create_task(worker(ip, port)) for ip, port in tasks]

    for _ in range(total):
        result = await queue.get()
        completed += 1
        pct = round((completed / total) * 100, 1)
        yield ScanProgress(
            type="result",
            completed=completed,
            total=total,
            progress_pct=pct,
            result=result,
        )

    await asyncio.gather(*worker_tasks, return_exceptions=True)
    yield ScanProgress(type="done", completed=total, total=total, progress_pct=100.0)
