"""
Leitura das fontes de dados: arquivos (JSON/CSV) e API da nuvem dos óculos.

Cada função lança uma exceção específica quando a fonte falha, para que o
orquestrador decida o que fazer (registrar, isolar o arquivo, seguir em frente).
Nada falha "em silêncio".
"""
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

EXTENSOES_ACEITAS = {".json", ".csv"}


class ArquivoInvalido(Exception):
    """O arquivo existe, mas não pôde ser lido ou está fora do formato."""


class FonteIndisponivel(Exception):
    """A API não respondeu depois de todas as tentativas."""


def listar_arquivos(pasta: Path) -> list[Path]:
    """Lista os arquivos da pasta de entrada em ordem alfabética (ignora .gitkeep)."""
    return sorted(p for p in pasta.iterdir() if p.is_file() and not p.name.startswith("."))


def _extrair_lista(dados, origem: str) -> list[dict]:
    """Aceita tanto uma lista de detecções quanto {"deteccoes": [...]}."""
    if isinstance(dados, dict):
        dados = dados.get("deteccoes")
    if not isinstance(dados, list):
        raise ArquivoInvalido(f"{origem}: formato inesperado (esperava uma lista de detecções)")
    return dados


def ler_arquivo(caminho: Path) -> list[dict]:
    """Lê um arquivo JSON ou CSV e devolve a lista de detecções (ainda não validadas)."""
    if caminho.suffix.lower() not in EXTENSOES_ACEITAS:
        raise ArquivoInvalido(f"{caminho.name}: extensão não suportada ({caminho.suffix or 'sem extensão'})")
    try:
        texto = caminho.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as erro:
        raise ArquivoInvalido(f"{caminho.name}: não foi possível ler o arquivo ({erro.__class__.__name__})")

    if not texto.strip():
        raise ArquivoInvalido(f"{caminho.name}: arquivo vazio")

    if caminho.suffix.lower() == ".json":
        try:
            return _extrair_lista(json.loads(texto), caminho.name)
        except json.JSONDecodeError as erro:
            raise ArquivoInvalido(f"{caminho.name}: JSON inválido (linha {erro.lineno})")

    leitor = csv.DictReader(texto.splitlines(), delimiter=";")
    if not leitor.fieldnames or "id_deteccao" not in leitor.fieldnames:
        raise ArquivoInvalido(f"{caminho.name}: CSV sem o cabeçalho esperado")
    return list(leitor)


def buscar_api(url: str, tentativas: int, timeout: float, espera_base: float, log) -> list[dict]:
    """
    Busca detecções na API da nuvem dos óculos, com novas tentativas
    e espera crescente (1s, 2s, 4s...). Se todas falharem, lança FonteIndisponivel.
    """
    ultimo_erro = ""
    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            registros = _extrair_lista(dados, "API")
            log.info("API respondeu na tentativa %d/%d com %d detecções", tentativa, tentativas, len(registros))
            return registros
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, ArquivoInvalido) as erro:
            ultimo_erro = f"{erro.__class__.__name__}: {getattr(erro, 'reason', erro)}"
            log.warning("API falhou na tentativa %d/%d (%s)", tentativa, tentativas, ultimo_erro)
            if tentativa < tentativas:
                time.sleep(espera_base * 2 ** (tentativa - 1))
    raise FonteIndisponivel(f"API indisponível após {tentativas} tentativas ({ultimo_erro})")
