from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_mosdns_binary.py"
SPEC = importlib.util.spec_from_file_location("verify_mosdns_binary", SCRIPT)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class DnsQueryTests(unittest.TestCase):
    def test_header_declares_one_question_with_recursion_desired(self):
        query = gate.build_dns_query("ad.example.com")
        self.assertEqual(len(query) >= 12, True)
        identifier, flags, qdcount, ancount, nscount, arcount = (
            int.from_bytes(query[0:2], "big"),
            int.from_bytes(query[2:4], "big"),
            int.from_bytes(query[4:6], "big"),
            int.from_bytes(query[6:8], "big"),
            int.from_bytes(query[8:10], "big"),
            int.from_bytes(query[10:12], "big"),
        )
        self.assertEqual(identifier, 0x5951)
        self.assertEqual(flags & 0x0100, 0x0100, "RD bit must be set")
        self.assertEqual((qdcount, ancount, nscount, arcount), (1, 0, 0, 0))

    def test_qname_is_length_prefixed_and_terminated(self):
        query = gate.build_dns_query("ad.example.com")
        self.assertTrue(query.endswith(b"\x00\x00\x01\x00\x01"), "QNAME/QTYPE/QCLASS tail")
        self.assertIn(b"\x02ad\x07example\x03com\x00", query)

    def test_rcode_is_read_from_the_low_nibble(self):
        # header + answer flags: QR=1, RD=1, RA=1, rcode=NXDOMAIN
        import socket
        import struct

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            def reply():
                data, addr = sock.recvfrom(2048)
                sock.sendto(data[:2] + struct.pack(">H", 0x8183) + data[4:], addr)

            import threading

            thread = threading.Thread(target=reply)
            thread.start()
            rcode, _ = gate.query_rcode(port, "blocked.example")
            thread.join(timeout=3)
        finally:
            sock.close()
        self.assertEqual(rcode, 3)


class StaticCheckTests(unittest.TestCase):
    def _write(self, directory: str, payload: bytes) -> Path:
        path = Path(directory) / "mosdns"
        path.write_bytes(payload)
        path.chmod(0o755)
        return path

    def test_unpatched_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = self._write(tmp, b"udp_server tcp_server forward sequence cache")
            failures = gate.static_check(binary)
        self.assertTrue(any("stats_api" in item for item in failures), failures)
        self.assertTrue(any("adblock_set" in item for item in failures), failures)

    def test_patched_build_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = self._write(
                tmp, b"stats_api adblock_set ip_set lazy_cache_ttl prefetch"
            )
            self.assertEqual(gate.static_check(binary), [])

    def test_missing_prefetch_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = self._write(tmp, b"stats_api adblock_set ip_set lazy_cache_ttl")
            failures = gate.static_check(binary)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("prefetch", failures[0])


class LocateBinaryTests(unittest.TestCase):
    def test_prefers_the_openwrt_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "usr" / "bin" / "mosdns"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"stats_api")
            target.chmod(0o755)
            self.assertEqual(gate.locate_binary(Path(tmp)), target)

    def test_returns_none_for_an_unrelated_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "README").write_text("nothing here", encoding="utf-8")
            self.assertIsNone(gate.locate_binary(Path(tmp)))


class ProbeVersionTests(unittest.TestCase):
    def test_unexecutable_binary_degrades_instead_of_raising(self):
        """回归：musl 目标在 glibc 容器里跑会 ENOENT，脚本不能因此崩掉。

        这是真发生过的失败——CI 里 execve 抛 FileNotFoundError，脚本带着
        traceback 退出，看起来像门禁坏了而不是"这里跑不了"。
        """
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "mosdns"
            binary.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
            binary.chmod(0o755)
            runs, detail = gate.probe_version(binary)
        self.assertFalse(runs)
        self.assertTrue(detail)

    def test_missing_binary_degrades_instead_of_raising(self):
        runs, detail = gate.probe_version(Path("/nonexistent/mosdns"))
        self.assertFalse(runs)
        self.assertTrue(detail)


class IdnaFallbackTests(unittest.TestCase):
    def test_hostname_socket_calls_survive_a_trimmed_python(self):
        """OpenWrt's python3 lacks encodings.idna; the fallback must restore it."""
        gate._ensure_idna_codec()
        gate._ensure_idna_codec()  # registering twice must stay harmless

        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.2)
            sock.sendto(gate.build_dns_query("probe.invalid"), ("127.0.0.1", sock.getsockname()[1]))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
