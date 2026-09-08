"""Repository-local IPv4 HTTPS for development and browser acceptance."""
import argparse
import ssl
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def https_server(directory, host="0.0.0.0", port=0, handler=SimpleHTTPRequestHandler):
    certs = ROOT / ".local-tool" / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    certificate, key = certs / "viewer.crt", certs / "viewer.key"
    if not certificate.exists() or not key.exists():
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(certificate), "-days", "3650",
            "-subj", "/CN=Model Structure development",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ], check=True, capture_output=True)
        key.chmod(0o600)
    server = ThreadingHTTPServer((host, port), partial(handler, directory=directory))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "build")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    server = https_server(args.directory, args.host, args.port)
    print(f"Serving https://{args.host}:{server.server_port}/; manually trust the self-signed certificate.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
