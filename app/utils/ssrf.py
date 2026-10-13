import ipaddress
import logging
import socket
import urllib.parse

from app.config import settings

logger = logging.getLogger(__name__)

# Carrier-Grade NAT (RFC 6598) and Cloud Metadata networks
CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")
CLOUD_METADATA_IP = ipaddress.ip_address("169.254.169.254")


class SSRFBlockedError(ValueError):
    """Raised when an outbound URL is directed at private, loopback, or metadata infrastructure."""

    pass


def is_ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP address is a safe, publicly routable address."""
    # Check for IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip == CLOUD_METADATA_IP
        or ip in CARRIER_GRADE_NAT
    ):
        return False

    return True


def validate_safe_url(url: str) -> None:
    """Validate that the given URL is safe from SSRF vulnerabilities.

    Raises SSRFBlockedError if the URL targets a restricted, local, or private resource.
    """
    if not settings.ENABLE_SSRF_PROTECTION:
        return

    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(
            f"Unsupported URL scheme '{scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL must contain a valid hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)
    if port not in (80, 443, 8000, 8080, 8443):
        raise SSRFBlockedError(f"Target port {port} is not an allowed HTTP port.")

    # Check for direct IP literal in hostname
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        if not is_ip_allowed(ip):
            raise SSRFBlockedError(
                f"Target IP address '{ip}' is private, loopback, or cloud metadata and is forbidden."
            )
        return
    except ValueError:
        # Not a raw IP literal, proceed to DNS resolution
        pass

    # Block well-known local hostnames directly
    lowered_host = hostname.lower()
    if (
        lowered_host in ("localhost", "local", "internal")
        or lowered_host.endswith(".local")
        or lowered_host.endswith(".internal")
    ):
        raise SSRFBlockedError(f"Target host '{hostname}' is reserved for local infrastructure.")

    # Resolve hostname via DNS
    try:
        addr_info = socket.getaddrinfo(
            hostname, parsed.port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Failed to resolve host '{hostname}': {exc}") from exc

    resolved_ips = set()
    for _, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            resolved_ips.add(ip)
        except ValueError:
            continue

    if not resolved_ips:
        raise SSRFBlockedError(f"Could not resolve any IP address for host '{hostname}'.")

    for ip in resolved_ips:
        if not is_ip_allowed(ip):
            raise SSRFBlockedError(
                f"Target host '{hostname}' resolved to forbidden address '{ip}'."
            )
