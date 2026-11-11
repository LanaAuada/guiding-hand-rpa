# Testes e validação

## Como rodar

```bash
python -m unittest -v
```

Resultado completo em [assets/testes_resultado.txt](../assets/testes_resultado.txt): **18 testes, 18 aprovados**.
Cada teste roda em uma pasta temporária, então não altera os dados reais.

## Testes automatizados

| # | Cenário | Tipo | Resultado esperado | Status |
|---|---|---|---|---|
| CT01 | 3 óculos diferentes veem o mesmo buraco | Sucesso | Barreira confirmada, publicada no GeoJSON e no CSV | ✅ |
| CT02 | Arquivo lido com sucesso | Sucesso | Arquivo movido para `processados/` | ✅ |
| CT03 | CSV com `;` e vírgula decimal | Sucesso | Detecção aceita | ✅ |
| CT04 | Só 2 óculos veem a barreira | Decisão | Fica pendente e não vai para o mapa | ✅ |
| CT05 | Pessoa e carro | Decisão | Ignorados (obstáculos móveis) | ✅ |
| CT06 | Confiança 0,3 | Decisão | Descartadas como ruído | ✅ |
| CT07 | Última detecção há 40 dias | Decisão | Possivelmente resolvida | ✅ |
| CT08 | Poste com 10 detecções | Decisão | Prioridade sobe de baixa para alta | ✅ |
| CT09 | Detecções chegam em dias diferentes | Decisão | Somam entre execuções até confirmar | ✅ |
| CT10 | JSON corrompido junto com um arquivo bom | Falha | Corrompido vai para quarentena, o bom é processado | ✅ |
| CT11 | Registros inválidos (fora de SP, tipo desconhecido, campos ausentes) | Falha | Rejeitados com motivo no log | ✅ |
| CT12 | Mesma detecção repetida no lote e reenviada depois | Falha | Contada uma só vez | ✅ |
| CT13 | API fora do ar | Falha | Tenta de novo, registra ERRO e segue com os arquivos | ✅ |
| CT14 | Pasta de entrada não existe | Falha | Pasta criada, execução segue | ✅ |
| CT15 | Estado corrompido | Falha | Backup criado, execução segue | ✅ |
| CT16 | Duas execuções | Auditoria | Duas linhas em `auditoria.jsonl` | ✅ |
| CT17 | ID real dos óculos | LGPD | Não aparece em logs, saídas nem estado | ✅ |
| CT18 | Coordenada exata | LGPD | Generalizada para a célula de ~30 m | ✅ |

## Execução de ponta a ponta (demonstração)

Saída completa em [assets/execucao_terminal.txt](../assets/execucao_terminal.txt), com os logs em [logs/](../logs/).

| Execução | Comando | O que mostra |
|---|---|---|
| 1 | `python -m src.main` | 60 detecções lidas, 33 aceitas, 4 inválidas, 2 duplicadas, 18 móveis, 3 de baixa confiança. 2 arquivos em quarentena. 4 barreiras confirmadas, 2 pendentes, 1 possivelmente resolvida |
| 2 | `--api http://localhost:8001/deteccoes` | API responde; o galho baixo visto por 3 óculos é confirmado |
| 3 | mesma API de novo | 4 duplicadas, nada é contado duas vezes |
| 4 | `--api http://localhost:9999/deteccoes` | 3 tentativas, ERRO registrado, status `concluida_com_alertas`, sem travar |
