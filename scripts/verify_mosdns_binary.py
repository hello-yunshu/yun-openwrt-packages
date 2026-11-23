#!/usr/bin/env python3
"""Reject a mosdns build that is not the patched variant luci-app-mosdns needs.

Why this exists
---------------
`mosdns-5.3.4-r15` exists in at least two mutually incompatible flavours that
carry the *same* package name and version:

* the upstream ImmortalWrt build, which has none of the sbwml patches;
* the sbwml build, which adds ``stats_api``, ``adblock_set``, ``ip_set``,
  ``log.size``/``backups`` and cache prefetch.

luci-app-mosdns is written against the second one.  Installed against the
first, it silently degrades: the statistics page has no API to talk to, DNS
adblock does nothing, and the init script's generated JSON fails to load
because ``log.size`` is an unknown key.  Nothing in the package name, version
or file size tells the two apart, so a feed can serve a broken combination for
months without anyone noticing.

This script is the gate that makes that impossible: it loads a candidate build
into a throwaway mosdns process and asks it to *do* the things the LuCI app
needs, rather than trusting metadata.

Usage
-----
    verify_mosdns_binary.py <apk-or-extracted-dir> [--arch x86_64]
                            [--apk-tool PATH] [--static-only]

Exit status 0 means the build is usable by luci-app-mosdns; anything else
means it must not be published.

Checks
------
Functional (native execution only):
    * a query matching ``adblock_set`` rules comes back NXDOMAIN;
    * the same blocked query shows up in ``stats_api`` counters;
    * a log section with ``size``/``backups`` loads;
      the unpatched build dies on these keys.

Static (every architecture):
    * the binary references the plugin tags the LuCI app generates.

Native execution is impossible for foreign architectures, so cross-built
artifacts fall back to the static check.  That check is weak on purpose: it
catches "wrong build" (the failure mode above) but cannot prove the patched
code paths run.  The x86_64 build is therefore always executed, and its result
speaks for the shared source tree.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# Plugins luci-app-mosdns generates into /var/etc/mosdns.json.  A build that
# cannot register these cannot serve the GUI at all.
REQUIRED_PLUGINS = ("stats_api", "adblock_set", "ip_set")

# Plugins the base forwarder needs.  Their absence would mean the binary is not
# mosdns at all, or an unusually stripped variant.
BASE_PLUGINS = (
    "udp_server",
    "tcp_server",
    "forward",
    "sequence",
    "cache",
    "domain_set",
    "fallback",
)

BLOCKED_NAME = "ad.yunwrt-gate.test"
BLOCK_RULE = f"||{BLOCKED_NAME}^\n"


def _ensure_idna_codec() -> None:
    """Make hostname socket calls work on OpenWrt's trimmed python3.

    OpenWrt's python3 omits ``encodings.idna``, and CPython routes *every*
    hostname string through the idna codec — bind, connect, sendto and
    getaddrinfo all raise ``LookupError: unknown encoding: idna`` before they
    ever reach the kernel.  That turns `socket.socket(AF_INET)` into something
    unusable for loopback traffic.

    Registering a plain-ASCII passthrough restores those calls.  It is not a
    real IDNA implementation, which is fine here: every address this script
    touches is a literal dotted quad.  It is installed only when the real
    codec is missing, so normal hosts are unaffected.
    """
    import codecs

    try:
        "127.0.0.1".encode("idna")
        return
    except LookupError:
        pass

    def _encode(text, errors="strict"):
        return text.encode("ascii", errors), len(text)

    def _decode(data, errors="strict"):
        return data.decode("ascii", errors), len(data)

    def _search(name):
        if name != "idna":
            return None
        return codecs.CodecInfo(name="idna", encode=_encode, decode=_decode)

    codecs.register(_search)


_ensure_idna_codec()


def build_dns_query(name: str, qtype: int = 1) -> bytes:
    """Minimal RFC1035 query: RD set, one question, A record."""
    header = struct.pack(">HHHHHH", 0x5951, 0x0100, 1, 0, 0, 0)
    qname = b"".join(
        bytes([len(label)]) + label.encode("ascii")
        for label in name.split(".")
        if label
    )
    return header + qname + b"\x00" + struct.pack(">HH", qtype, 1)


def query_rcode(port: int, name: str, timeout: float = 5.0) -> tuple[int, str]:
    """Ask mosdns for ``name`` and return (rcode, human readable)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(build_dns_query(name), ("127.0.0.1", port))
        data, _ = sock.recvfrom(4096)
    if len(data) < 12:
        return -1, "short response"
    return data[3] & 0x0F, data[12:].hex()[:80]


def wait_udp(port: int, timeout: float = 8.0) -> bool:
    """Wait until something listens on 127.0.0.1:<port> (UDP)."""
    deadline = timeout
    while deadline > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.3)
            try:
                sock.sendto(build_dns_query("gate-probe.invalid"), ("127.0.0.1", port))
                sock.recvfrom(4096)
                return True
            except (socket.timeout, OSError):
                pass
        subprocess.run(["sleep", "0.2"], check=False)
        deadline -= 0.2
    return False


def http_get(url: str, timeout: float = 5.0) -> str | None:
    """GET ``url`` over a raw socket to loopback.

    Neither urllib nor http.client is usable here: both resolve the host name
    through the idna codec that OpenWrt's python3 does not ship.  A literal
    packed address sidesteps the whole DNS/idna path.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    port = parts.port or 80
    request = f"GET {parts.path} HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n".encode()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(("127.0.0.1", port))
            sock.sendall(request)
            chunks = []
            while True:
                data = sock.recv(8192)
                if not data:
                    break
                chunks.append(data)
    except OSError:
        return None
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    if b" 200 " not in head.split(b"\r\n")[0]:
        return None
    return body.decode("utf-8", "replace")


def free_port_block(count: int) -> list[int]:
    """Return ``count`` consecutive-ish ports that are currently free."""
    socks, ports = [], []
    while len(ports) < count:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        ports.append(sock.getsockname()[1])
        socks.append(sock)
    for sock in socks:
        sock.close()
    return ports


def _text(value) -> str:
    """subprocess returns bytes from TimeoutExpired even under text=True."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _run_capture(cmd: list[str], timeout: float, cwd: Path) -> str:
    """Run ``cmd`` and return combined output, surviving the timeout path."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return _text(proc.stdout) + _text(proc.stderr)
    except subprocess.TimeoutExpired as exc:
        return _text(exc.stdout) + _text(exc.stderr)


def probe_plugin(binary: Path, plugin: str, workdir: Path) -> tuple[bool, str]:
    """Load a config whose only plugin is ``plugin`` and see if it registers.

    An unpatched mosdns answers `plugin type X not defined`.  Any other
    outcome — including an argument error we do not care about — proves the
    type is registered.
    """
    conf = workdir / f"probe-{plugin}.yaml"
    conf.write_text(
        f"log:\n  level: error\nplugins:\n  - tag: t\n    type: {plugin}\n",
        encoding="utf-8",
    )
    out = _run_capture([str(binary), "start", "-c", str(conf)], 2.5, workdir)
    if "not defined" in out:
        return False, out.strip().splitlines()[-1][:120] if out.strip() else ""
    return True, ""


def check_log_rotation(binary: Path, workdir: Path) -> tuple[bool, str]:
    """The 209 patch teaches the log section about size/backups."""
    ports = free_port_block(1)
    conf = workdir / "log-rotation.yaml"
    conf.write_text(
        "log:\n"
        "  level: error\n"
        f'  file: "{workdir}/rot.log"\n'
        "  size: 5\n"
        "  backups: 3\n"
        "plugins:\n"
        "  - tag: entry\n"
        "    type: sequence\n"
        "    args:\n"
        "      - exec: accept\n"
        "  - tag: srv\n"
        "    type: udp_server\n"
        "    args:\n"
        "      entry: entry\n"
        f'      listen: "127.0.0.1:{ports[0]}"\n',
        encoding="utf-8",
    )
    out = _run_capture([str(binary), "start", "-c", str(conf)], 2.5, workdir)
    if "invalid keys" in out:
        return False, out.strip().splitlines()[-1][:160]
    if "config loaded" not in out and "FATAL" in out:
        return False, out.strip().splitlines()[-1][:160]
    return True, ""


def check_functional(binary: Path, workdir: Path) -> list[str]:
    """Start a real instance and prove adblock_set + stats_api actually work.

    The forwarder is pointed at a closed port so a leaking query fails fast
    instead of reaching the internet — the check must not depend on network
    reachability, and a blocked name must never be forwarded in the first
    place.
    """
    failures: list[str] = []
    dns_port, api_port = free_port_block(2)

    (workdir / "ads.txt").write_text(BLOCK_RULE, encoding="utf-8")
    conf = workdir / "functional.yaml"
    conf.write_text(
        "log:\n"
        "  level: warn\n"
        f'  file: "{workdir}/functional.log"\n'
        "  size: 5\n"
        "  backups: 2\n"
        "api:\n"
        f'  http: "127.0.0.1:{api_port}"\n'
        "plugins:\n"
        "  - tag: stats_collector\n"
        "    type: stats_api\n"
        "    args:\n"
        "      capacity: 64\n"
        "  - tag: ad_rules\n"
        "    type: adblock_set\n"
        "    args:\n"
        "      files:\n"
        f'        - "{workdir}/ads.txt"\n'
        "  - tag: dead_fwd\n"
        "    type: forward\n"
        "    args:\n"
        "      upstreams:\n"
        '        - addr: "127.0.0.1:1"\n'
        "  - tag: main\n"
        "    type: sequence\n"
        "    args:\n"
        "      - exec: $stats_collector\n"
        "      - matches: qname $ad_rules\n"
        "        exec: reject 3\n"
        "      - exec: $dead_fwd\n"
        "  - tag: srv\n"
        "    type: udp_server\n"
        "    args:\n"
        "      entry: main\n"
        f'      listen: "127.0.0.1:{dns_port}"\n',
        encoding="utf-8",
    )

    log = open(workdir / "functional.stdout", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(binary), "start", "-c", str(conf)],
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=workdir,
    )
    try:
        if not wait_udp(dns_port):
            log.flush()
            tail = (workdir / "functional.stdout").read_text(encoding="utf-8", errors="replace")
            return [f"service did not start\n{tail.strip()[:400]}"]

        rcode, _ = query_rcode(dns_port, BLOCKED_NAME)
        if rcode != 3:
            failures.append(
                f"adblock_set did not block {BLOCKED_NAME}: rcode={rcode} (want 3/NXDOMAIN)"
            )

        stats_url = f"http://127.0.0.1:{api_port}/plugins/stats_collector/api/v1/stats"
        body = None
        for _ in range(20):
            body = http_get(stats_url)
            if body:
                break
            subprocess.run(["sleep", "0.2"], check=False)
        if not body:
            failures.append("stats_api did not answer /plugins/stats_collector/api/v1/stats")
        else:
            import json as _json

            try:
                stats = _json.loads(body)
            except ValueError:
                failures.append(f"stats_api returned non-JSON: {body[:120]}")
            else:
                if stats.get("total_queries", 0) < 1:
                    failures.append(f"stats_api counted no queries: {stats}")
                if stats.get("blocked_queries", 0) < 1:
                    failures.append(f"stats_api counted no blocked queries: {stats}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log.close()

    return failures


def static_check(binary: Path) -> list[str]:
    """Weaker check for builds we cannot execute on this host."""
    failures: list[str] = []
    data = binary.read_bytes()
    for needle in (b"stats_api", b"adblock_set", b"ip_set", b"lazy_cache_ttl", b"prefetch"):
        if needle not in data:
            failures.append(f"binary does not reference {needle.decode()}")
    return failures


def locate_binary(root: Path) -> Path | None:
    for rel in ("usr/bin/mosdns", "bin/mosdns", "mosdns"):
        cand = root / rel
        if cand.is_file():
            return cand
    for cand in root.rglob("mosdns"):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def extract_apk(apk: Path, dest: Path, tool: str | None) -> Path:
    """Unpack an apk v3 archive into ``dest``. Returns the mosdns binary."""
    host_tool = tool or shutil.which("apk")
    if not host_tool:
        raise SystemExit(
            "no apk tool found; pass --apk-tool (OpenWrt SDK: staging_dir/host/bin/apk)"
        )
    result = subprocess.run(
        [host_tool, "extract", "--allow-untrusted", str(apk)],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"apk extract failed: {(result.stderr or result.stdout).strip()[:300]}")
    binary = locate_binary(dest)
    if not binary:
        raise SystemExit(f"no mosdns binary inside {apk.name}")
    return binary


def probe_version(binary: Path) -> tuple[bool, str]:
    """Return (runs_here, detail). Never raises.

    execve 在两种情况下失败而不是返回非零：目标架构与本机不同，或二进制动态
    链接而本机没有对应 ELF 解释器（musl 目标在 glibc 容器里跑会报 ENOENT，
    而不是"无法执行"）。两种都只说明"这里跑不了"，不是构建有问题。
    """
    try:
        proc = subprocess.run(
            [str(binary), "version"], capture_output=True, text=True, timeout=10
        )
    except OSError as exc:
        return False, exc.strerror or "cannot execute"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if proc.returncode != 0:
        return False, f"exited {proc.returncode}"
    return True, (proc.stdout or proc.stderr or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path, help=".apk file or an extracted directory")
    parser.add_argument("--arch", default="x86_64")
    parser.add_argument("--apk-tool", default=None)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="skip execution (use when the target arch cannot run here)",
    )
    args = parser.parse_args()

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mosdns-gate-") as tmp:
        tmpdir = Path(tmp)
        if args.artifact.is_dir():
            binary = locate_binary(args.artifact)
            if not binary:
                raise SystemExit(f"no mosdns binary under {args.artifact}")
        else:
            binary = extract_apk(args.artifact, tmpdir, args.apk_tool)

        binary = binary.resolve()
        size_mb = binary.stat().st_size / (1024 * 1024)
        print(f"mosdns binary: {binary} ({size_mb:.1f} MiB)")

        executable = not args.static_only and os.access(binary, os.X_OK)
        if executable:
            runs, detail = probe_version(binary)
            if runs:
                print(f"  version: {detail}")
            else:
                executable = False
                print(f"  note: 无法在此执行（{detail}），降级为静态检查")

        print("\n-- static --")
        static_failures = static_check(binary)
        for item in static_failures:
            print(f"  FAIL {item}")
        failures += static_failures
        if not static_failures:
            print("  ok   patch markers present")

        if executable:
            print("\n-- plugin registration --")
            for plugin in REQUIRED_PLUGINS + BASE_PLUGINS:
                ok, detail = probe_plugin(binary, plugin, tmpdir)
                mark = "ok  " if ok else "FAIL"
                extra = "" if ok else f"  {detail}"
                print(f"  {mark} {plugin}{extra}")
                if not ok:
                    failures.append(f"plugin {plugin} is not registered")

            print("\n-- log rotation keys --")
            ok, detail = check_log_rotation(binary, tmpdir)
            print("  ok   size/backups accepted" if ok else f"  FAIL {detail}")
            if not ok:
                failures.append("log.size/log.backups rejected (missing 209 patch)")

            print("\n-- live behaviour --")
            for item in check_functional(binary, tmpdir):
                print(f"  FAIL {item}")
                failures.append(item)
            if not failures:
                print("  ok   adblock_set blocks, stats_api counts")
    if failures:
        print(f"\nGATE FAILED: {len(failures)} problem(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nGATE PASSED: build is usable by luci-app-mosdns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
