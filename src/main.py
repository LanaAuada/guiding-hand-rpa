"""
Guiding Hand · Automação de confirmação de barreiras (RPA)

Fluxo (ver docs/fluxo_automacao.bpmn):
  1. Carrega o estado (mapa de barreiras conhecido).
  2. Coleta detecções da API (se configurada) e dos arquivos da pasta de entrada.
  3. Para CADA detecção: valida, descarta duplicadas/móveis/baixa confiança, agrupa.
  4. Para CADA barreira: decide o status (pendente, confirmada, possivelmente resolvida).
  5. Salva o estado e publica: mapa GeoJSON (MVP), relatório CSV (zeladoria), resumo.
  6. Registra log detalhado e trilha de auditoria.

Uso:
  python -m src.main                       # só arquivos de data/entrada
  python -m src.main --api http://localhost:8001/deteccoes
"""
import argparse
import logging
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import leitura, regras, saida
from .config import Config


def configurar_log(pasta_logs: Path, id_execucao: str, na_tela: bool = True) -> tuple[logging.Logger, Path]:
    pasta_logs.mkdir(parents=True, exist_ok=True)
    caminho = pasta_logs / f"execucao_{id_execucao}.log"
    log = logging.getLogger(f"guiding_hand.{id_execucao}")
    log.setLevel(logging.DEBUG)
    log.propagate = False

    arquivo = logging.FileHandler(caminho, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    tela = logging.StreamHandler(sys.stdout)
    tela.setLevel(logging.INFO)
    tela.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
    log.addHandler(arquivo)
    if na_tela:
        log.addHandler(tela)
    return log, caminho


def fechar_log(log: logging.Logger) -> None:
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


def mover(arquivo: Path, destino: Path, id_execucao: str) -> Path:
    """Move o arquivo para processados/rejeitados com o ID da execução no nome (evita sobrescrever)."""
    destino.mkdir(parents=True, exist_ok=True)
    novo = destino / f"{id_execucao}_{arquivo.name}"
    shutil.move(str(arquivo), novo)
    return novo


def processar_registro(registro, estado, ids_vistos, cfg, cont, log) -> None:
    """Aplica as regras R1 a R5 a UMA detecção e a soma à barreira correspondente."""
    cont["lidos"] += 1
    det, motivo = regras.validar(registro)
    id_ref = str(registro.get("id_deteccao", "sem-id"))[:40] if isinstance(registro, dict) else "sem-id"

    if motivo:                                                  # R1
        cont["invalidos"] += 1
        log.warning("Detecção %s rejeitada: %s", id_ref, motivo)
        return
    if det["id_deteccao"] in ids_vistos:                        # R2
        cont["duplicados"] += 1
        log.debug("Detecção %s ignorada: duplicada", id_ref)
        return
    ids_vistos.add(det["id_deteccao"])

    if det["tipo"] in regras.TIPOS_MOVEIS:                      # R3
        cont["ignorados_moveis"] += 1
        log.debug("Detecção %s ignorada: obstáculo móvel (%s)", id_ref, det["tipo"])
        return
    if det["confianca"] < cfg.confianca_minima:                 # R4
        cont["baixa_confianca"] += 1
        log.debug("Detecção %s descartada: confiança %.2f", id_ref, det["confianca"])
        return

    lat, lon = regras.celula(det["latitude"], det["longitude"], cfg.tamanho_celula)  # R5
    chave = regras.chave_barreira(lat, lon, det["tipo"])
    quando = det["data_hora"].isoformat(timespec="seconds")
    barreira = estado["barreiras"].setdefault(chave, {
        "id": regras.id_barreira(chave), "tipo": det["tipo"], "latitude": lat, "longitude": lon,
        "status": "pendente", "prioridade": regras.TIPOS_FIXOS[det["tipo"]][1],
        "total_deteccoes": 0, "soma_confianca": 0.0, "dispositivos": [],
        "primeira_deteccao": quando, "ultima_deteccao": quando,
    })
    barreira["total_deteccoes"] += 1
    barreira["soma_confianca"] = round(barreira["soma_confianca"] + det["confianca"], 4)
    hash_disp = regras.anonimizar(det["id_dispositivo"], cfg.salt)
    if hash_disp not in barreira["dispositivos"]:
        barreira["dispositivos"].append(hash_disp)
    barreira["primeira_deteccao"] = min(barreira["primeira_deteccao"], quando)
    barreira["ultima_deteccao"] = max(barreira["ultima_deteccao"], quando)
    cont["aceitos"] += 1


def reavaliar_barreiras(estado, cfg, data_ref, log) -> dict:
    """Aplica R6, R7 e R8 a CADA barreira e conta as mudanças de status."""
    mudancas = {"novas_confirmadas": 0, "novas_resolvidas": 0, "reabertas": 0}
    for b in estado["barreiras"].values():
        antigo = b["status"]
        novo = regras.definir_status(b, data_ref, cfg.min_dispositivos, cfg.dias_para_resolvida)
        b["prioridade"] = regras.definir_prioridade(b["tipo"], b["total_deteccoes"], cfg.deteccoes_prioridade_alta)
        if novo == antigo:
            continue
        b["status"] = novo
        if novo == "confirmada" and antigo == "possivelmente_resolvida":
            mudancas["reabertas"] += 1
        elif novo == "confirmada":
            mudancas["novas_confirmadas"] += 1
        elif novo == "possivelmente_resolvida":
            mudancas["novas_resolvidas"] += 1
        log.info("Barreira %s (%s): %s -> %s | %d óculos, %d detecções, prioridade %s",
                 b["id"], b["tipo"], antigo, novo, len(b["dispositivos"]), b["total_deteccoes"], b["prioridade"])
    return mudancas


def executar(cfg: Config | None = None, data_ref: datetime | None = None) -> dict:
    cfg = cfg or Config()
    inicio = datetime.now()
    data_ref = data_ref or inicio
    id_execucao = f"{inicio:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}"
    log, caminho_log = configurar_log(cfg.pasta_logs, id_execucao, cfg.mostrar_na_tela)
    t0 = time.perf_counter()

    cont = dict.fromkeys(["lidos", "aceitos", "invalidos", "duplicados", "ignorados_moveis", "baixa_confianca", "erros"], 0)
    fontes = {"arquivos_lidos": 0, "arquivos_rejeitados": 0, "api": "nao_configurada"}
    alertas, gerados, mudancas = [], [], {}
    status = "sucesso"
    estado = {"ids_processados": [], "barreiras": {}}

    try:
        log.info("=== Início da execução %s ===", id_execucao)
        for pasta in (cfg.pasta_entrada, cfg.pasta_processados, cfg.pasta_rejeitados, cfg.pasta_estado, cfg.pasta_saida):
            if not pasta.exists():
                log.warning("Pasta %s não existia e foi criada", pasta.name)
                pasta.mkdir(parents=True, exist_ok=True)

        estado = saida.carregar_estado(cfg.pasta_estado, log)
        ids_vistos = set(estado["ids_processados"])

        # ---- 2. Coleta: API ------------------------------------------------
        lotes: list[tuple[str, list]] = []
        if cfg.api_url:
            try:
                lotes.append(("API", leitura.buscar_api(cfg.api_url, cfg.api_tentativas, cfg.api_timeout, cfg.api_espera_base, log)))
                fontes["api"] = "ok"
            except leitura.FonteIndisponivel as erro:
                fontes["api"] = "indisponivel"
                alertas.append(str(erro))
                log.error("%s. Seguindo apenas com os arquivos locais", erro)

        # ---- 2. Coleta: arquivos (repetição sobre a pasta) -------------------
        lidos_ok: list[Path] = []
        for arquivo in leitura.listar_arquivos(cfg.pasta_entrada):
            try:
                registros = leitura.ler_arquivo(arquivo)
                lotes.append((arquivo.name, registros))
                lidos_ok.append(arquivo)
                fontes["arquivos_lidos"] += 1
                log.info("Arquivo %s lido: %d detecções", arquivo.name, len(registros))
            except leitura.ArquivoInvalido as erro:
                fontes["arquivos_rejeitados"] += 1
                alertas.append(str(erro))
                destino = mover(arquivo, cfg.pasta_rejeitados, id_execucao)
                log.error("%s. Movido para quarentena: %s", erro, destino.name)

        if not lotes:
            log.warning("Nenhuma detecção nova para processar")

        # ---- 3. Repetição sobre cada detecção --------------------------------
        for origem, registros in lotes:
            for registro in registros:
                try:
                    processar_registro(registro, estado, ids_vistos, cfg, cont, log)
                except Exception as erro:  # um registro ruim nunca derruba o lote
                    cont["erros"] += 1
                    log.exception("Erro inesperado em registro de %s: %s", origem, erro.__class__.__name__)

        # ---- 4. Decisão sobre cada barreira ----------------------------------
        mudancas = reavaliar_barreiras(estado, cfg, data_ref, log)

        # ---- 5. Persistência e publicação ------------------------------------
        estado["ids_processados"] = sorted(ids_vistos)
        saida.salvar_estado(cfg.pasta_estado, estado)
        for arquivo in lidos_ok:  # só move depois de salvar: se algo falhar antes, o arquivo é reprocessado
            mover(arquivo, cfg.pasta_processados, id_execucao)

        gerados.append(saida.exportar_geojson(cfg.pasta_saida, estado, inicio).name)
        gerados.append(saida.exportar_relatorio_zeladoria(cfg.pasta_saida, estado, inicio).name)

        if cont["invalidos"]:
            alertas.append(f"{cont['invalidos']} detecções inválidas rejeitadas (ver log)")
        if cont["erros"]:
            alertas.append(f"{cont['erros']} registros com erro inesperado (ver log)")
        if alertas:
            status = "concluida_com_alertas"

    except Exception as erro:
        status = "falha"
        alertas.append(f"Falha crítica: {erro.__class__.__name__}: {erro}")
        log.critical("Execução interrompida por falha crítica", exc_info=True)

    barreiras = list(estado["barreiras"].values())
    resumo = {
        "execucao": id_execucao,
        "inicio": inicio.isoformat(timespec="seconds"),
        "duracao_segundos": round(time.perf_counter() - t0, 3),
        "status": status,
        "fontes": fontes,
        "deteccoes": cont,
        "barreiras": {
            "total_conhecidas": len(barreiras),
            "confirmadas": sum(b["status"] == "confirmada" for b in barreiras),
            "pendentes": sum(b["status"] == "pendente" for b in barreiras),
            "possivelmente_resolvidas": sum(b["status"] == "possivelmente_resolvida" for b in barreiras),
            **mudancas,
        },
        "alertas": alertas,
        "arquivos_gerados": gerados,
        "log": caminho_log.name,
    }
    if status != "falha":
        saida.exportar_resumo(cfg.pasta_saida, resumo)
    saida.registrar_auditoria(cfg.pasta_logs, resumo)

    log.info("Detecções: %d lidas | %d aceitas | %d inválidas | %d duplicadas | %d móveis | %d baixa confiança | %d erros",
             cont["lidos"], cont["aceitos"], cont["invalidos"], cont["duplicados"],
             cont["ignorados_moveis"], cont["baixa_confianca"], cont["erros"])
    b = resumo["barreiras"]
    log.info("Barreiras: %d confirmadas | %d pendentes | %d possivelmente resolvidas",
             b["confirmadas"], b["pendentes"], b["possivelmente_resolvidas"])
    log.info("=== Fim da execução: %s (%.2fs) ===", status.upper(), resumo["duracao_segundos"])
    fechar_log(log)
    return resumo


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # acentos corretos no terminal do Windows
    parser = argparse.ArgumentParser(description="Guiding Hand: confirma barreiras e atualiza o mapa")
    parser.add_argument("--api", help="URL da API de detecções (opcional)")
    args = parser.parse_args()
    cfg = Config()
    if args.api:
        cfg.api_url = args.api
    resumo = executar(cfg)
    return 1 if resumo["status"] == "falha" else 0


if __name__ == "__main__":
    sys.exit(main())
