#!/usr/bin/env python3
"""Exercise the real installer against a local TLS release origin.

The production script has no runtime origin override. This test substitutes the
origin and certificate trust only in a temporary source copy.
"""
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading

REPO = Path(__file__).resolve().parents[1]
TARGETS = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-amd64": "x86_64-apple-darwin",
    "linux-amd64": "x86_64-unknown-linux-musl",
    "linux-arm64": "aarch64-unknown-linux-musl",
}
PASSWORD = "synthetic-preview-" + os.urandom(12).hex()
state = {"requests": [], "user_agents": [], "mode": "", "transform": None, "version": "v0.16.0"}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        authorized = self.headers.get("Authorization") is not None
        state["requests"].append((self.path, authorized))
        state["user_agents"].append(self.headers.get("User-Agent"))
        if state["mode"] == "unauthorized":
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Godmode preview"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        manifest_request = self.path.endswith(".json")
        if (manifest_request and state["mode"] == "redirect-manifest") or (
                not manifest_request and state["mode"] == "redirect-artifact"):
            self.send_response(302)
            self.send_header("Location", "https://127.0.0.1:" + str(self.server.server_port) + "/credential-trap")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if manifest_request:
            if self.path not in ("/releases/latest.json", "/releases/" + state["version"] + "/manifest.json"):
                self.send_error(404)
                return
            doc = copy.deepcopy(state["manifest"])
            if state["transform"]:
                state["transform"](doc)
            payload = json.dumps(doc).encode()
            if state["mode"] == "duplicate-json":
                payload = b'{"version":"v0.16.0",' + payload[1:]
            if state["mode"] == "oversized-manifest":
                payload = b" " * (128 * 1024 + 1)
        else:
            filename = self.path.rsplit("/", 1)[-1]
            if filename not in state["artifacts"] or state["mode"] == "missing-artifact":
                self.send_error(404)
                return
            payload = state["artifacts"][filename]
            if state["mode"] == "tamper":
                payload = bytes([payload[0] ^ 1]) + payload[1:]
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if manifest_request else "application/gzip")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not manifest_request and state["mode"] == "truncated":
            payload = payload[:-7]
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

def archive(program, installer):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, value, mode in [("godmode", program, 0o755), ("install.sh", installer, 0o755)]:
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(value), mode
            tar.addfile(member, io.BytesIO(value))
    return data.getvalue()

with tempfile.TemporaryDirectory(prefix="godmode-transport-") as directory:
    root = Path(directory)
    cert, key = root / "tls.pem", root / "tls.key"
    config = root / "tls.cnf"
    config.write_text("""[req]
distinguished_name=dn
x509_extensions=ext
prompt=no
[dn]
CN=localhost
[ext]
subjectAltName=DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:TRUE
keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign
""")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-days", "1", "-keyout", str(key), "-out", str(cert), "-config", str(config)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        production = (REPO / "install.sh").read_text()
        origin_line = 'ORIGIN = "https://godmode.build"'
        assert production.count(origin_line) == 1, "production origin must be fixed"
        assert "github.com/" not in production, "installer retained GitHub transport"
        local_origin = "https://localhost:" + str(server.server_port)
        fixture = production.replace(origin_line, "ORIGIN = " + repr(local_origin))
        assert fixture.count("ssl.create_default_context()") == 1
        untrusted_fixture = fixture
        fixture = fixture.replace("ssl.create_default_context()", "ssl.create_default_context(cafile=" + repr(str(cert)) + ")")
        installer = root / "install.sh"
        installer.write_text(fixture)
        installer.chmod(0o755)
        temp = root / "tmp"
        temp.mkdir()
        clean_path = ":".join(p for p in os.environ["PATH"].split(":") if not (Path(p) / "godmode").exists())
        base_env = dict(os.environ, PATH=clean_path, SHELL="/bin/sh", LC_ALL="C", TERM="dumb",
                        TMPDIR=str(temp), GODMODE_PREVIEW_PASSWORD=PASSWORD)
        for name in ("GODMODE_HOME", "ZDOTDIR"):
            base_env.pop(name, None)

        def release(version):
            state.update(version=version, mode="", transform=None)
            program = ("#!/bin/sh\nprintf 'godmode " + version[1:] + "\\n'\n").encode()
            packed = archive(program, fixture.encode())
            entries = []
            state["artifacts"] = {}
            for platform, target in TARGETS.items():
                filename = "godmode-" + version + "-" + target + ".tar.gz"
                state["artifacts"][filename] = packed
                entries.append({"platform": platform, "filename": filename,
                                "sha256": hashlib.sha256(packed).hexdigest(), "size": len(packed)})
            state["manifest"] = {
                "version": version, "artifacts": entries,
                "source": {"filename": "godmode-" + version + "-source.tar.gz", "sha256": "a" * 64, "size": 100},
            }
            return program

        def run(home, *args, expected=0, env=None, command=None):
            variables = dict(base_env, HOME=str(home))
            if env:
                variables.update(env)
            result = subprocess.run(command or ["sh", str(installer), "--install-only", *args],
                                    env=variables, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True, timeout=20)
            assert result.returncode == expected if expected == 0 else result.returncode != 0, (
                result.returncode, result.stdout.decode(), result.stderr.decode())
            assert PASSWORD.encode() not in result.stdout + result.stderr, "password appeared in output"
            assert not list(temp.iterdir()), "download residue survived"
            return result

        release("v0.16.0")
        first = root / "first"
        output = run(first)
        assert (first / ".godmode/bin/godmode").read_bytes().startswith(b"#!/bin/sh")
        assert b"To set up, run:" in output.stdout
        assert b"Activate:" not in output.stdout
        assert len(state["requests"]) == 2 and not any(auth for _, auth in state["requests"])
        assert state["user_agents"] == ["godmode-installer/3", "godmode-installer/3"]
        for path in (first / ".godmode/bin").iterdir():
            if path.is_file():
                assert PASSWORD.encode() not in path.read_bytes(), "password persisted"
        assert (first / ".godmode/bin/godmode").stat().st_mode & 0o777 == 0o755
        assert (first / ".godmode/bin/.godmode-install-receipt").stat().st_mode & 0o777 == 0o600

        # Existing installations are refused before networking.
        state["requests"].clear()
        run(first, expected=1)
        assert not state["requests"]

        # Up-to-date uses only the manifest; explicit force reinstalls.
        updater = first / ".godmode/bin/godmodeup"
        before = (first / ".godmode/bin/.godmode-install-receipt").read_bytes()
        current = run(first, command=[str(updater)])
        assert b"0.16.0 is up to date" in current.stdout
        assert state["requests"] == [("/releases/latest.json", False)]
        assert (first / ".godmode/bin/.godmode-install-receipt").read_bytes() == before
        state["requests"].clear()
        run(first, command=[str(updater), "--force"])
        assert len(state["requests"]) == 2

        # Pin selects exactly that manifest. Runtime API/origin variables do not redirect it.
        state["requests"].clear()
        run(root / "pinned", "--version", "v0.16.0",
            env={"GODMODE_DOWNLOAD_ORIGIN": "https://untrusted.invalid", "GODMODE_API_URL": "https://untrusted.invalid"})
        assert state["requests"][0] == ("/releases/v0.16.0/manifest.json", False)
        state["requests"].clear()
        run(root / "unsafe-pin", "--version", "v0.16.0\n../outside", expected=1)
        assert not state["requests"] and not (root / "unsafe-pin").exists()

        # Explicit PATH setup appends one line and preserves an existing startup file.
        path_home = root / "path-home"
        path_home.mkdir()
        startup = path_home / ".zshenv"
        startup.write_text("export USER_SETTING=keep\n")
        run(path_home, "--path", env={"SHELL": "/bin/zsh"})
        assert startup.read_text().startswith("export USER_SETTING=keep\n")
        backups = list(path_home.glob(".zshenv.godmode-backup.*"))
        assert len(backups) == 1 and backups[0].read_text() == "export USER_SETTING=keep\n"
        run(path_home, env={"SHELL": "/bin/zsh"}, command=[str(path_home / ".godmode/bin/godmodeup"), "--path"])
        assert startup.read_text().count("# Godmode") == 1

        state["transform"] = lambda doc: doc.update(version="v0.16.1")
        run(root / "mismatched-pin", "--version", "v0.16.0", expected=1)
        assert not (root / "mismatched-pin").exists()
        state["transform"] = None

        # HTTP failures, redirects, truncated archives and altered bytes install nothing.
        for mode in ("unauthorized", "redirect-manifest", "redirect-artifact", "missing-artifact", "tamper",
                     "truncated", "duplicate-json", "oversized-manifest"):
            state.update(mode=mode, requests=[])
            home = root / mode
            run(home, expected=1)
            assert not home.exists(), mode
            assert all(path != "/credential-trap" for path, _ in state["requests"]), "redirect was followed"
        state["mode"] = ""
        # Legacy password variables are never sent. Public downloads need no stdin.
        ignored = run(root / "ignored-password", env={"GODMODE_PREVIEW_PASSWORD": "incorrect-fixture-password"})
        assert b"incorrect-fixture-password" not in ignored.stdout + ignored.stderr
        assert not any(auth for _, auth in state["requests"])
        # An untrusted TLS certificate is refused.
        unsafe_cert_script = root / "untrusted-install.sh"
        unsafe_cert_script.write_text(untrusted_fixture)
        denied = run(root / "bad-certificate", expected=1,
                     command=["sh", str(unsafe_cert_script), "--install-only"])
        assert b"verified HTTPS" in denied.stderr

        transforms = [
            lambda d: d["artifacts"][0].update(filename="../outside.tar.gz"),
            lambda d: d["artifacts"][0].update(filename="/tmp/outside.tar.gz"),
            lambda d: d["artifacts"][0].update(filename="godmode-v0.16.0-a;touch.tar.gz"),
            lambda d: d["artifacts"][0].update(size=True),
            lambda d: d["artifacts"][0].update(size=0),
            lambda d: d["artifacts"][0].update(size=300 * 1024 * 1024),
            lambda d: d["artifacts"][0].update(sha256="not-a-digest"),
            lambda d: d["artifacts"].append(d["artifacts"][0]),
            lambda d: d["artifacts"][0].update(platform="unknown"),
            lambda d: d["source"].update(filename="../source.tar.gz"),
            lambda d: d.pop("source"),
            lambda d: d.update(version="v0.16.0\n../../outside"),
            lambda d: d.update(unexpected=True),
        ]
        for index, transform in enumerate(transforms):
            state["transform"] = transform
            home = root / ("schema-" + str(index))
            run(home, expected=1)
            assert not home.exists()
        state["transform"] = None

        # A changed release leaves a verified rollback; failed subsequent downloads preserve it.
        old = (first / ".godmode/bin/godmode").read_bytes()
        new = release("v0.16.1")
        run(first, command=[str(updater)])
        assert (first / ".godmode/bin/godmode").read_bytes() == new
        assert (first / ".godmode/bin/godmode.previous").read_bytes() == old
        preserved = {p.name: p.read_bytes() for p in (first / ".godmode/bin").iterdir() if p.is_file()}
        release("v0.16.2")
        state["mode"] = "tamper"
        run(first, command=[str(updater)], expected=1)
        assert {p.name: p.read_bytes() for p in (first / ".godmode/bin").iterdir() if p.is_file()} == preserved
        state["mode"] = ""
        state["requests"].clear()
        offline = root / "offline.tar.gz"
        offline.write_bytes(next(iter(state["artifacts"].values())))
        sums = root / "SHA256SUMS"
        sums.write_text(hashlib.sha256(offline.read_bytes()).hexdigest() + "  offline.tar.gz\n")
        run(first, command=[str(updater), "--archive", str(offline), "--checksum", str(sums)])
        assert not state["requests"], "offline update contacted a server"
        assert b"godmode 0.16.2" in (first / ".godmode/bin/godmode").read_bytes()

        assert not any(auth for _, auth in state["requests"]), "installer sent an Authorization header"
        assert not list(temp.iterdir())
    finally:
        server.shutdown()
        server.server_close()

print("HTTPS installer tests passed (accountless install, no credential headers, TLS, redirects, pins, schemas, tamper, rollback and offline update).")
