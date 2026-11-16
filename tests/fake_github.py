"""A tiny stand-in for the parts of the GitHub REST API that the CI scripts call.

Served endpoints:
- ``GET /repos/<owner>/<name>/pulls/<n>/reviews``
- ``GET /repos/<owner>/<name>/pulls/<n>``
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PULL_PATH = re.compile(r"^/repos/[^/]+/[^/]+/pulls/(\d+)(/reviews)?$")


class FakeGitHub:
    """Holds pull requests in memory and serves them over HTTP on localhost."""

    def __init__(self):
        # PR number -> {"user": {"login": ...}, "merge_commit_sha": ..., "reviews": [...]}
        self.pulls: dict[int, dict] = {}
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def add_pull(self, number: int, author: str) -> None:
        self.pulls[number] = {"number": number, "user": {"login": author}, "merge_commit_sha": None, "reviews": []}

    def approve(self, number: int, reviewer: str) -> None:
        self.pulls[number]["reviews"].append({"user": {"login": reviewer}, "state": "APPROVED"})

    def _make_handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                match = PULL_PATH.match(self.path)
                if not match or int(match.group(1)) not in fake.pulls:
                    self._send(404, {"message": "Not Found"})
                    return
                pull = fake.pulls[int(match.group(1))]
                if match.group(2):
                    self._send(200, pull["reviews"])
                else:
                    self._send(200, {key: value for key, value in pull.items() if key != "reviews"})

            def _send(self, status: int, body) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        return Handler
