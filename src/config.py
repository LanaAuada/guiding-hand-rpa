"""
Configurações da automação.

Tudo que pode mudar sem alterar o código fica aqui: pastas, regras de negócio
e parâmetros de resiliência. Valores sensíveis (como o "salt" usado para
anonimizar os dispositivos) vêm de variáveis de ambiente, nunca do código.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    # --- Pastas ---------------------------------------------------------
    pasta_entrada: Path = RAIZ / "data" / "entrada"        # arquivos enviados pela nuvem dos óculos
    pasta_processados: Path = RAIZ / "data" / "processados"  # arquivos já lidos com sucesso
    pasta_rejeitados: Path = RAIZ / "data" / "rejeitados"    # arquivos ilegíveis (quarentena)
    pasta_estado: Path = RAIZ / "data" / "estado"            # "banco" interno da automação
    pasta_saida: Path = RAIZ / "saida"                       # o que o MVP e a zeladoria consomem
    pasta_logs: Path = RAIZ / "logs"
    mostrar_na_tela: bool = True   # False nos testes (o log em arquivo continua completo)

    # --- Fonte API (opcional) ---------------------------------------------
    api_url: str | None = field(default_factory=lambda: os.getenv("GH_API_URL"))
    api_tentativas: int = 3        # quantas vezes tenta antes de desistir
    api_timeout: float = 5.0       # segundos por tentativa
    api_espera_base: float = 1.0   # espera entre tentativas: 1s, 2s, 4s...

    # --- Segurança / LGPD -------------------------------------------------
    salt: str = field(default_factory=lambda: os.getenv("GH_SALT", "salt-de-desenvolvimento"))

    # --- Regras de negócio ------------------------------------------------
    min_dispositivos: int = 3          # R6: barreira confirmada com 3+ óculos diferentes
    confianca_minima: float = 0.5      # R4: abaixo disso a detecção é ruído
    tamanho_celula: float = 0.0003     # R5: ~30 m; generaliza a localização
    dias_para_resolvida: int = 30      # R8: sem detecção há 30 dias = possivelmente resolvida
    deteccoes_prioridade_alta: int = 10  # R7: muitas detecções elevam a prioridade
