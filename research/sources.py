import re
import ipaddress
import socket
import urllib.parse
import urllib.request
from html import unescape


def open_source(url, max_chars=12000):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("only http and https URLs are allowed")
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("the URL has no hostname")
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(hostname, None)]
        except socket.gaierror as error:
            raise ValueError("could not resolve the source hostname") from error
    if any(address.is_private or address.is_loopback or address.is_link_local for address in addresses):
        raise ValueError("private and local URLs are not allowed")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Rubi-Assistant/Stage5"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(max_chars * 4).decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )
    raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.I | re.S)
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:max_chars]
