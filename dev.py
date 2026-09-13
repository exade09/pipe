"""Local run of exactly what Vercel runs: the API plus web/dist on one port."""
from http.server import ThreadingHTTPServer
import sys
sys.path.insert(0, ".")
from api.index import handler

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"pipe terminal on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
