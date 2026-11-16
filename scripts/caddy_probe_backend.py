"""Disposable Caddy-test upstream/client only; never deployed as an Atlas service."""

import hashlib
import http.client
import json
import socket
import ssl
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


# Return synthetic headers/counts so tests distinguish denial from accidental application proxying.
class Probe(BaseHTTPRequestHandler):
    count = 0

    # Health/count reads are inert; ordinary proxy requests increment independent evidence.
    def do_GET(self):
        if self.path == "/counter":
            value = {"count": Probe.count}
        elif self.path in {"/health/ready", "/health/live"}:
            value = {"status": "ready"}
        else:
            Probe.count += 1
            value = {"headers": dict(self.headers), "path": self.path}
        content = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # Never log presented headers or credentials even in disposable fixtures.
    def log_message(self, *args):
        return


# Internal DNS routing and TLS verification remain independent for negative SNI tests.
class VerifiedHttps(http.client.HTTPSConnection):
    # Retain CA/hostname verification; only the explicit test SNI may differ from transport DNS.
    def connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=3)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.test_sni)


# Send bounded requests inside the isolated Docker network; publish no host ports.
def request():
    values = json.loads(sys.stdin.buffer.read(16384))
    assert values["target"] in {"atlas.example.test", "otm-api", "pebble"}
    if values["method"] == "PORT_CLOSED":
        try:
            with socket.create_connection(
                (values["target"], values["port"]), timeout=3
            ):
                return {"port_closed": False}
        except ConnectionRefusedError:
            return {"port_closed": True}
    if values["tls"]:
        assert values["ca"] in {"server.crt", "issuance-root.crt"}
        context = ssl.create_default_context(cafile="/test-trust/" + values["ca"])
        connection = VerifiedHttps(
            values["target"], values["port"], context=context, timeout=3
        )
        connection.test_sni = values["sni"]
    else:
        connection = http.client.HTTPConnection(
            values["target"], values["port"], timeout=3
        )
    try:
        if values["method"] == "CERTIFICATE":
            connection.connect()
            return {
                "certificate": hashlib.sha256(
                    connection.sock.getpeercert(binary_form=True)
                ).hexdigest()
            }
        connection.request(values["method"], values["path"], headers=values["headers"])
        response = connection.getresponse()
        return {
            "status": response.status,
            "body": response.read(1048576).decode(),
            "headers": response.getheaders(),
        }
    except ssl.SSLError:
        return {"tls_error": True}
    finally:
        connection.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(request()))
    else:
        # Test container only; no host listener exists when importing this fixture.
        HTTPServer(("0.0.0.0", 8080), Probe).serve_forever()  # nosec B104
