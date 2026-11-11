"""
Persistência e publicação dos resultados.

- Estado interno (data/estado/barreiras.json): o "banco" da automação.
- mapa_barreiras.geojson: consumido pelo MVP (mapa no app e cálculo de rotas).
- relatorio_zeladoria_AAAA-MM-DD.csv: enviado à zeladoria (abre no Excel).
- resumo_execucao.json: indicadores da última execução (painel do MVP).

Toda gravação é atômica (grava em .tmp e renomeia), para o MVP nunca ler
um arquivo pela metade.
"""
import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .regras import ORDEM_PRIORIDADE, TIPOS_FIXOS


def gravar_atomico(caminho: Path, conteudo: str, encoding: str = "utf-8") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(conteudo, encoding=encoding, newline="")
    os.replace(temporario, caminho)


def carregar_estado(pasta_estado: Path, log) -> dict:
    """Carrega o estado. Se estiver corrompido, guarda uma cópia e recomeça (sem parar a automação)."""
    caminho = pasta_estado / "barreiras.json"
    vazio = {"ids_processados": [], "barreiras": {}}
    if not caminho.exists():
        log.info("Estado inexistente: iniciando um mapa de barreiras novo")
        return vazio
    try:
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        if not isinstance(estado.get("barreiras"), dict) or not isinstance(estado.get("ids_processados"), list):
            raise ValueError("estrutura inesperada")
        log.info("Estado carregado: %d barreiras conhecidas", len(estado["barreiras"]))
        return estado
    except (json.JSONDecodeError, ValueError, AttributeError) as erro:
        backup = caminho.with_name(f"barreiras_corrompido_{datetime.now():%Y%m%d_%H%M%S}.json")
        caminho.replace(backup)
        log.error("Estado corrompido (%s). Cópia salva em %s; iniciando estado novo", erro, backup.name)
        return vazio


def salvar_estado(pasta_estado: Path, estado: dict) -> None:
    gravar_atomico(pasta_estado / "barreiras.json", json.dumps(estado, ensure_ascii=False, indent=2))


def _publicas(estado: dict) -> list[dict]:
    """Barreiras que saem para o MVP/zeladoria (pendentes ainda não foram confirmadas)."""
    lista = [b for b in estado["barreiras"].values() if b["status"] != "pendente"]
    return sorted(lista, key=lambda b: (ORDEM_PRIORIDADE[b["prioridade"]], b["status"], b["id"]))


def exportar_geojson(pasta_saida: Path, estado: dict, gerado_em: datetime) -> Path:
    """Integração com o MVP. Não contém nenhum identificador de dispositivo."""
    features = []
    for b in _publicas(estado):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [b["longitude"], b["latitude"]]},
            "properties": {
                "id": b["id"],
                "tipo": b["tipo"],
                "descricao": TIPOS_FIXOS[b["tipo"]][0],
                "status": b["status"],
                "prioridade": b["prioridade"],
                "total_deteccoes": b["total_deteccoes"],
                "dispositivos_distintos": len(b["dispositivos"]),
                "confianca_media": round(b["soma_confianca"] / b["total_deteccoes"], 2),
                "primeira_deteccao": b["primeira_deteccao"],
                "ultima_deteccao": b["ultima_deteccao"],
            },
        })
    geojson = {
        "type": "FeatureCollection",
        "metadata": {"gerado_em": gerado_em.isoformat(timespec="seconds"), "fonte": "Guiding Hand RPA"},
        "features": features,
    }
    caminho = pasta_saida / "mapa_barreiras.geojson"
    gravar_atomico(caminho, json.dumps(geojson, ensure_ascii=False, indent=2))
    return caminho


def exportar_relatorio_zeladoria(pasta_saida: Path, estado: dict, gerado_em: datetime) -> Path:
    """CSV com ; e BOM para abrir direto no Excel em português."""
    linhas = [["id", "descricao", "prioridade", "status", "latitude", "longitude",
               "total_deteccoes", "dispositivos_distintos", "ultima_deteccao", "link_mapa"]]
    for b in _publicas(estado):
        linhas.append([
            b["id"], TIPOS_FIXOS[b["tipo"]][0], b["prioridade"], b["status"],
            f"{b['latitude']:.6f}", f"{b['longitude']:.6f}",
            b["total_deteccoes"], len(b["dispositivos"]), b["ultima_deteccao"][:16].replace("T", " "),
            f"https://www.google.com/maps?q={b['latitude']:.6f},{b['longitude']:.6f}",
        ])
    caminho = pasta_saida / f"relatorio_zeladoria_{gerado_em:%Y-%m-%d}.csv"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".csv.tmp")
    with temporario.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=";").writerows(linhas)
    os.replace(temporario, caminho)
    return caminho


def exportar_resumo(pasta_saida: Path, resumo: dict) -> Path:
    caminho = pasta_saida / "resumo_execucao.json"
    gravar_atomico(caminho, json.dumps(resumo, ensure_ascii=False, indent=2))
    return caminho


def registrar_auditoria(pasta_logs: Path, resumo: dict) -> None:
    """Trilha de auditoria: uma linha JSON por execução (só acrescenta, nunca apaga)."""
    pasta_logs.mkdir(parents=True, exist_ok=True)
    with (pasta_logs / "auditoria.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(resumo, ensure_ascii=False) + "\n")
