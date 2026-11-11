"""
Regras de negócio da automação.

R1  Validação: campos obrigatórios, tipos e valores coerentes.
R2  Duplicidade: a mesma detecção (id_deteccao) só conta uma vez, mesmo entre execuções.
R3  Obstáculos móveis (pessoa, ciclista, animal, carro) não viram barreira no mapa.
R4  Detecções com confiança abaixo do mínimo são descartadas como ruído.
R5  A localização é generalizada para uma célula de ~30 m (LGPD).
R6  Uma barreira só é CONFIRMADA quando vista por 3+ óculos diferentes.
R7  Prioridade para a zeladoria: pelo tipo de risco e pela quantidade de detecções.
R8  Barreira confirmada sem detecção há 30 dias vira POSSIVELMENTE_RESOLVIDA.
"""
import hashlib
from datetime import datetime

CAMPOS_OBRIGATORIOS = ["id_deteccao", "id_dispositivo", "data_hora", "latitude", "longitude", "tipo", "confianca"]

# Obstáculos fixos: tipo -> (descrição para a zeladoria, prioridade base)
TIPOS_FIXOS = {
    "buraco":            ("Buraco na calçada", "alta"),
    "galho_baixo":       ("Galho na altura da cabeça", "alta"),
    "placa_baixa":       ("Placa na altura da cabeça", "alta"),
    "cacamba":           ("Caçamba na calçada", "alta"),
    "entulho":           ("Entulho no percurso", "alta"),
    "orelhao":           ("Orelhão (obstáculo acima da cintura)", "media"),
    "calcada_irregular": ("Calçada irregular", "media"),
    "lixeira":           ("Lixeira no percurso", "media"),
    "poste":             ("Poste no meio da calçada", "baixa"),
}
TIPOS_MOVEIS = {"pessoa", "ciclista", "animal", "carro"}

# Área do piloto: município de São Paulo (aproximado)
LAT_MIN, LAT_MAX = -24.01, -23.35
LON_MIN, LON_MAX = -46.83, -46.36

ORDEM_PRIORIDADE = {"alta": 0, "media": 1, "baixa": 2}


def anonimizar(id_dispositivo: str, salt: str) -> str:
    """LGPD: o identificador real dos óculos nunca é guardado, só um hash com salt."""
    return hashlib.sha256(f"{salt}:{id_dispositivo}".encode()).hexdigest()[:16]


def validar(registro: dict) -> tuple[dict | None, str | None]:
    """
    R1. Devolve (detecção normalizada, None) se estiver ok,
    ou (None, motivo) se o registro for inválido.
    """
    if not isinstance(registro, dict):
        return None, "registro não é um objeto"

    faltando = [c for c in CAMPOS_OBRIGATORIOS if str(registro.get(c) or "").strip() == ""]
    if faltando:
        return None, f"campos ausentes: {', '.join(faltando)}"

    try:
        lat = float(str(registro["latitude"]).replace(",", "."))
        lon = float(str(registro["longitude"]).replace(",", "."))
        confianca = float(str(registro["confianca"]).replace(",", "."))
    except ValueError:
        return None, "latitude, longitude ou confiança não numérica"

    try:
        data_hora = datetime.fromisoformat(str(registro["data_hora"]).strip())
    except ValueError:
        return None, "data_hora fora do formato ISO (AAAA-MM-DDTHH:MM:SS)"
    data_hora = data_hora.replace(tzinfo=None)

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None, "coordenada fora da área do piloto (São Paulo)"
    if not 0 <= confianca <= 1:
        return None, "confiança fora do intervalo 0 a 1"

    tipo = str(registro["tipo"]).strip().lower()
    if tipo not in TIPOS_FIXOS and tipo not in TIPOS_MOVEIS:
        return None, f"tipo de obstáculo desconhecido: {tipo}"

    return {
        "id_deteccao": str(registro["id_deteccao"]).strip(),
        "id_dispositivo": str(registro["id_dispositivo"]).strip(),
        "data_hora": data_hora,
        "latitude": lat,
        "longitude": lon,
        "tipo": tipo,
        "confianca": confianca,
    }, None


def celula(lat: float, lon: float, tamanho: float) -> tuple[float, float]:
    """R5. Arredonda a posição para o centro de uma célula de ~30 m."""
    return round(round(lat / tamanho) * tamanho, 6), round(round(lon / tamanho) * tamanho, 6)


def chave_barreira(lat: float, lon: float, tipo: str) -> str:
    return f"{lat:.6f}|{lon:.6f}|{tipo}"


def id_barreira(chave: str) -> str:
    """Identificador estável: a mesma barreira sempre recebe o mesmo ID."""
    return "GH-" + hashlib.sha1(chave.encode()).hexdigest()[:8].upper()


def definir_prioridade(tipo: str, total_deteccoes: int, limite: int) -> str:
    """R7. Prioridade base do tipo; muitas detecções elevam para alta."""
    base = TIPOS_FIXOS[tipo][1]
    return "alta" if total_deteccoes >= limite else base


def definir_status(barreira: dict, data_ref: datetime, min_dispositivos: int, dias_resolvida: int) -> str:
    """R6 e R8. Decide o status da barreira."""
    dias_sem_ver = (data_ref - datetime.fromisoformat(barreira["ultima_deteccao"])).days
    confirmada = len(barreira["dispositivos"]) >= min_dispositivos

    if confirmada and dias_sem_ver > dias_resolvida:
        return "possivelmente_resolvida"
    if confirmada:
        return "confirmada"
    return "pendente"
