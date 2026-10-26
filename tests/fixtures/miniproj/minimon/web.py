"""HTTP 로 사용률 보여 주기."""

from http.server import BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    """요청 처리기."""

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_response(200)
        elif path in ("/disk", "/disk.json"):
            self.send_response(200)
        else:
            self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/reset":
            self.send_response(204)
            self.end_headers()
