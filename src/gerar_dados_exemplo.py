"""
Gera dados de exemplo que simulam o que a nuvem dos óculos envia à automação.

Os dados foram montados para exercitar todas as regras:
  - barreiras vistas por 3+ óculos (confirmam), por 1-2 óculos (ficam pendentes);
  - uma barreira antiga, sem detecção há 40 dias (possivelmente resolvida);
  - pessoas e carros (ignorados), detecções de baixa confiança (descartadas);
  - registros inválidos, duplicados, um arquivo corrompido e um com extensão errada.

ATENÇÃO: limpa as pastas data/ e saida/ antes de gerar (reinicia a demonstração).

Uso: python -m src.gerar_dados_exemplo
"""
import csv
import json
import random
import shutil
from datetime import datetime, timedelta

from .config import Config

random.seed(42)
AGORA = datetime.now().replace(microsecond=0)
CELULA = Config().tamanho_celula

# Bairro piloto: República / Centro de São Paulo
PONTOS = {
    "buraco":            (-23.5440, -46.6422),
    "placa_baixa":       (-23.5452, -46.6407),
    "lixeira":           (-23.5461, -46.6395),
    "entulho":           (-23.5470, -46.6419),
    "poste":             (-23.5434, -46.6389),
    "cacamba":           (-23.5419, -46.6416),
    "orelhao":           (-23.5449, -46.6431),
    "galho_baixo":       (-23.5431, -46.6440),
}
_contador = 0


def deteccao(tipo, dispositivo, horas_atras, confianca=None, ponto=None, prefixo="DET"):
    global _contador
    _contador += 1
    lat, lon = ponto or PONTOS.get(tipo, (-23.5445, -46.6410))
    lat = round(round(lat / CELULA) * CELULA + random.uniform(-0.00008, 0.00008), 6)  # ~8 m de variação de GPS
    lon = round(round(lon / CELULA) * CELULA + random.uniform(-0.00008, 0.00008), 6)
    return {
        "id_deteccao": f"{prefixo}-{_contador:05d}",
        "id_dispositivo": f"OCL-{dispositivo:04d}",
        "data_hora": (AGORA - timedelta(hours=horas_atras, minutes=random.randint(0, 59))).isoformat(),
        "latitude": lat,
        "longitude": lon,
        "tipo": tipo,
        "confianca": confianca if confianca is not None else round(random.uniform(0.62, 0.97), 2),
    }


def lote_json():
    d = []
    d += [deteccao("buraco", disp, random.randint(1, 30)) for disp in (1, 2, 3, 4, 5, 2, 3, 1)]   # 5 óculos -> confirmada
    d += [deteccao("placa_baixa", disp, random.randint(1, 30)) for disp in (2, 6, 7, 8)]          # 4 óculos -> confirmada
    d += [deteccao("lixeira", disp, random.randint(1, 48)) for disp in (1, 4, 9) * 4][:11]         # 11 detecções -> prioridade sobe p/ alta
    d += [deteccao("entulho", disp, 24 * 40 + random.randint(0, 20)) for disp in (3, 5, 7)]       # 40 dias atrás -> possivelmente resolvida
    d += [deteccao("pessoa", random.randint(1, 9), random.randint(1, 10), ponto=(-23.5445, -46.6410)) for _ in range(15)]
    d += [deteccao("carro", disp, 3) for disp in (1, 2, 3)]
    d += [deteccao("galho_baixo", disp, 2, confianca=0.31) for disp in (4, 5, 6)]                 # confiança baixa -> descartadas
    return d


def lote_csv(ja_enviados):
    d = []
    d += [deteccao("poste", disp, random.randint(1, 30)) for disp in (1, 6, 8)]                   # 3 óculos -> confirmada (prioridade baixa)
    d += [deteccao("cacamba", disp, random.randint(1, 30)) for disp in (2, 4, 2)]                 # 2 óculos -> pendente
    d += [deteccao("orelhao", 7, 5)]                                                              # 1 óculo  -> pendente
    d += [dict(ja_enviados[0]), dict(ja_enviados[1])]                                             # duplicadas do lote JSON
    invalidos = [
        deteccao("buraco", 3, 2, ponto=(-22.9068, -43.1729)),  # Rio de Janeiro: fora da área do piloto
        deteccao("buraco", 3, 2),
        deteccao("banco_de_praca", 3, 2),
        deteccao("placa_baixa", 3, 2),
    ]
    invalidos[1]["tipo"] = ""                    # campo obrigatório vazio
    invalidos[3]["data_hora"] = "31/02/2026"     # data inválida
    return d + invalidos


def deteccoes_api():
    """Detecções que a API simulada devolve: um galho visto por 3 óculos."""
    random.seed(7)
    return [deteccao("galho_baixo", disp, 1, prefixo="API") for disp in (10, 11, 12, 10)]


def main():
    cfg = Config()
    for pasta in (cfg.pasta_entrada, cfg.pasta_processados, cfg.pasta_rejeitados, cfg.pasta_estado, cfg.pasta_saida):
        shutil.rmtree(pasta, ignore_errors=True)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / ".gitkeep").touch()

    primeiro = lote_json()
    (cfg.pasta_entrada / "deteccoes_oculos_lote1.json").write_text(
        json.dumps({"origem": "nuvem-guiding-hand", "deteccoes": primeiro}, ensure_ascii=False, indent=2), encoding="utf-8")

    segundo = lote_csv(primeiro)
    with (cfg.pasta_entrada / "deteccoes_oculos_lote2.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(segundo[0].keys()), delimiter=";")
        escritor.writeheader()
        escritor.writerows(segundo)

    (cfg.pasta_entrada / "deteccoes_oculos_lote3.json").write_text('{"deteccoes": [ {"id_deteccao": "X"', encoding="utf-8")
    (cfg.pasta_entrada / "anotacoes_operador.txt").write_text("arquivo enviado por engano", encoding="utf-8")

    print(f"Dados de exemplo gerados em {cfg.pasta_entrada}:")
    for arquivo in sorted(cfg.pasta_entrada.iterdir()):
        if arquivo.name != ".gitkeep":
            print(f"  - {arquivo.name}")


if __name__ == "__main__":
    main()
