"""
API simulada da nuvem dos óculos (para demonstração e testes).

Uso: python -m src.api_simulada
Depois, em outro terminal: python -m src.main --api http://localhost:8001/deteccoes
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .gerar_dados_exemplo import deteccoes_api

PORTA = 8001
DADOS = deteccoes_api()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/deteccoes"):
            corpo = json.dumps({"deteccoes": DADOS}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(corpo)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    print(f"API simulada em http://localhost:{PORTA}/deteccoes  (Ctrl+C para parar)")
    HTTPServer(("localhost", PORTA), Handler).serve_forever()
