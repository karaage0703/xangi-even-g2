"""Adopt a socket bound by the managed runtime, or bind for standalone use."""
import os
import socket
from http.server import ThreadingHTTPServer


def create_server(host, port, handler):
    descriptor = os.environ.get("EVEN_LISTEN_FD")
    if descriptor is None:
        return ThreadingHTTPServer((host, port), handler)
    server = ThreadingHTTPServer((host, port), handler, bind_and_activate=False)
    server.socket.close()
    server.socket = socket.socket(fileno=int(descriptor))
    server.server_address = server.socket.getsockname()
    server.server_name = socket.getfqdn(host)
    server.server_port = server.server_address[1]
    return server
