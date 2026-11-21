"""Proxy de salida de Gemelo: aplica la política de red de cada caja.

Corre en su propio contenedor, conectado a la red `gemelo_internal` (sin salida)
y a `gemelo_egress` (con salida). Es el único puente entre ambas.

Proxy (puerto 3128, solo en las redes Docker):
  - CONNECT host:port (HTTPS) y HTTP con URL absoluta.
  - La caja se identifica por su IP de origen. IP sin política: se niega.
  - Políticas: open (todo), gateway_only (solo ALWAYS), isolated (ALWAYS + allowlist).
  - Destinos a IP privada o link-local se niegan salvo los de ALWAYS.

Admin (puerto 3129, publicado solo en 127.0.0.1 del host), con Bearer ADMIN_TOKEN:
  PUT    /policies/<ip>   {"run_id","lane","role","kind","allowlist":[...]}
  DELETE /policies/<ip>   borra y corta los túneles vivos de esa IP
  GET    /policies

Cada decisión se reporta a EVENTS_URL (orquestador) en segundo plano.
Solo biblioteca estándar.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
ALWAYS = {x.strip().lower() for x in os.environ.get("ALWAYS", "").split(",") if x.strip()}
EVENTS_URL = os.environ.get("EVENTS_URL", "")
# Destinos privados que una caja con política open sí puede alcanzar (atacante local de desarrollo)
OPEN_ALSO = {x.strip().lower() for x in os.environ.get("OPEN_ALSO", "").split(",") if x.strip()}
PROXY_PORT = int(os.environ.get("PROXY_PORT", "3128"))
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "3129"))

POLICIES: dict[str, dict] = {}
TUNNELS: dict[str, set[asyncio.StreamWriter]] = {}
_pool = ThreadPoolExecutor(4)


def report(ip: str, host: str, port: int, decision: str, reason: str) -> None:
    if not EVENTS_URL:
        return
    pol = POLICIES.get(ip, {})
    body = json.dumps({"ip": ip, "run_id": pol.get("run_id"), "lane": pol.get("lane"), "role": pol.get("role"),
                       "host": host, "port": port, "decision": decision, "reason": reason}).encode()

    def send():
        try:
            req = urllib.request.Request(EVENTS_URL, data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {ADMIN_TOKEN}"})
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3).read()
        except Exception:
            pass

    _pool.submit(send)


def _is_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def decide(src_ip: str, host: str, port: int) -> tuple[bool, str]:
    host = host.lower().strip("[]")
    hp = f"{host}:{port}"
    pol = POLICIES.get(src_ip)
    if pol is None:
        return False, "caja sin política"
    if hp in ALWAYS:
        return True, "always"
    kind = pol.get("kind")
    if kind == "open":
        if hp in OPEN_ALSO:
            return True, "open"
        if _is_private(host):
            return False, "destino privado"
        return True, "open"
    if kind == "isolated":
        for a in pol.get("allowlist", []):
            a = a.lower()
            if host == a or host.endswith("." + a):
                if _is_private(host):
                    return False, "destino privado"
                return True, "allowlist"
        return False, "fuera de la allowlist"
    return False, "solo gateway"


async def pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def deny(w: asyncio.StreamWriter, reason: str) -> None:
    body = f"blocked by gemelo egress policy: {reason}\n".encode()
    w.write(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nX-Gemelo: blocked\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    try:
        await w.drain()
    finally:
        w.close()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    src_ip = writer.get_extra_info("peername")[0]
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    except Exception:
        writer.close()
        return
    lines = head.decode("latin-1").split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        writer.close()
        return

    if method.upper() == "CONNECT":
        host, _, port_s = target.rpartition(":")
        port = int(port_s or 443)
        ok, reason = decide(src_ip, host, port)
        report(src_ip, host, port, "allow" if ok else "deny", reason)
        if not ok:
            await deny(writer, reason)
            return
        try:
            ur, uw = await asyncio.wait_for(asyncio.open_connection(host.strip("[]"), port), timeout=15)
        except Exception:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            writer.close()
            return
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        TUNNELS.setdefault(src_ip, set()).update({writer, uw})
        try:
            await asyncio.gather(pipe(reader, uw), pipe(ur, writer))
        finally:
            TUNNELS.get(src_ip, set()).difference_update({writer, uw})
        return

    u = urllib.parse.urlsplit(target)
    if u.scheme != "http" or not u.hostname:
        await deny(writer, "solo HTTP absoluto o CONNECT")
        return
    host, port = u.hostname, u.port or 80
    ok, reason = decide(src_ip, host, port)
    report(src_ip, host, port, "allow" if ok else "deny", reason)
    if not ok:
        await deny(writer, reason)
        return
    path = urllib.parse.urlunsplit(("", "", u.path or "/", u.query, ""))
    out = [f"{method} {path} {version}"]
    for h in lines[1:]:
        if not h:
            continue
        name = h.split(":", 1)[0].strip().lower()
        if name.startswith("proxy-") or name == "connection":
            continue
        out.append(h)
    out.append("Connection: close")
    try:
        ur, uw = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=15)
    except Exception:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        writer.close()
        return
    uw.write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
    await uw.drain()
    TUNNELS.setdefault(src_ip, set()).update({writer, uw})
    try:
        await asyncio.gather(pipe(reader, uw), pipe(ur, writer))
    finally:
        TUNNELS.get(src_ip, set()).difference_update({writer, uw})


def cut(ip: str) -> None:
    for w in list(TUNNELS.pop(ip, set())):
        try:
            w.close()
        except Exception:
            pass


async def admin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {k.strip().lower(): v.strip() for k, _, v in (h.partition(":") for h in lines[1:] if h)}
        body = await reader.readexactly(int(headers.get("content-length", "0") or 0))
        if headers.get("authorization") != f"Bearer {ADMIN_TOKEN}" or not ADMIN_TOKEN:
            status, resp = "401 Unauthorized", {"error": "auth"}
        elif method == "GET" and path == "/policies":
            status, resp = "200 OK", POLICIES
        elif path.startswith("/policies/") and method == "PUT":
            ip = path.rsplit("/", 1)[1]
            pol = json.loads(body or b"{}")
            prev = POLICIES.get(ip, {}).get("kind")
            POLICIES[ip] = pol
            if prev and prev != pol.get("kind"):
                cut(ip)  # al endurecer la política, se cortan los túneles vivos
            status, resp = "200 OK", {"ok": True}
        elif path.startswith("/policies/") and method == "DELETE":
            ip = path.rsplit("/", 1)[1]
            POLICIES.pop(ip, None)
            cut(ip)
            status, resp = "200 OK", {"ok": True}
        elif path == "/health":
            status, resp = "200 OK", {"ok": True}
        else:
            status, resp = "404 Not Found", {"error": "not found"}
    except Exception as e:
        status, resp = "400 Bad Request", {"error": str(e)}
    data = json.dumps(resp).encode()
    writer.write(f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n"
                 f"Connection: close\r\n\r\n".encode() + data)
    await writer.drain()
    writer.close()


async def main() -> None:
    proxy = await asyncio.start_server(handle, "0.0.0.0", PROXY_PORT)
    adm = await asyncio.start_server(admin, "0.0.0.0", ADMIN_PORT)
    print(f"gemelo egress proxy :{PROXY_PORT}, admin :{ADMIN_PORT}, always={sorted(ALWAYS)}", flush=True)
    async with proxy, adm:
        await asyncio.gather(proxy.serve_forever(), adm.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
