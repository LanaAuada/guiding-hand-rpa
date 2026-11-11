# Roteiro do vídeo (até 3 minutos)

Dica: grave a tela com o OBS ou com a Barra de Jogos do Windows (`Win + Alt + R`). Deixe abertos antes de começar:
um terminal na pasta do projeto, um segundo terminal com `python -m src.api_simulada` e um terceiro com
`python -m http.server 8000`.

| Tempo | Tela | Fala (sugestão) |
|---|---|---|
| 0:00–0:25 | Slide ou README | "O Guiding Hand são óculos que avisam pessoas cegas sobre obstáculos. Cada obstáculo detectado vira um registro. O problema: são milhares de registros por dia, com pessoas, carros e erros misturados. Conferir isso à mão para atualizar o mapa e avisar a zeladoria seria impossível. A nossa automação faz isso sozinha." |
| 0:25–0:45 | `docs/fluxo_automacao.png` | "O robô carrega o mapa atual, lê a API dos óculos e os arquivos, valida cada detecção, agrupa as próximas e decide: só confirma a barreira quando três óculos diferentes a viram." |
| 0:45–1:00 | Terminal: `python -m src.gerar_dados_exemplo` e mostrar `data/entrada` | "Aqui estão os dados de entrada: dois lotes bons, um JSON corrompido e um arquivo enviado por engano." |
| 1:00–1:35 | Terminal: `python -m src.main` | "O robô rejeita os dois arquivos ruins e manda para a quarentena, rejeita detecções fora de São Paulo ou sem tipo, ignora pessoas e carros. Veja a decisão: o buraco foi visto por 5 óculos e foi confirmado; a caçamba, só por 2, fica pendente; o entulho não aparece há 40 dias e vira possivelmente resolvido." |
| 1:35–1:55 | Terminal: `python -m src.main --api http://localhost:8001/deteccoes` | "Agora com a API: um galho na altura da cabeça, visto por 3 óculos, é confirmado." |
| 1:55–2:15 | Terminal: `python -m src.main --api http://localhost:9999/deteccoes` | "E se a API cair? O robô tenta três vezes, registra o erro e termina com alerta, sem travar e sem falhar em silêncio." |
| 2:15–2:40 | Navegador: `http://localhost:8000/mvp/` e abrir o CSV no Excel | "Essa é a integração com o MVP: o app lê o mapa GeoJSON gerado e mostra as barreiras por prioridade. A zeladoria recebe a planilha com o link de cada ponto no mapa." |
| 2:40–3:00 | `logs/execucao_*.log` e `auditoria.jsonl` | "Tudo fica registrado com data e hora, sem o identificador dos óculos, seguindo a LGPD. Temos 18 testes automatizados cobrindo sucesso, decisão e falha. Obrigado!" |
