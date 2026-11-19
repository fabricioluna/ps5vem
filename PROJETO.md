# Monitor de Ofertas do PS5

## Objetivo

Sistema simples que monitora o preço do **PlayStation 5 Slim Edição Digital com Astro Bot** (pacote com ou sem Gran Turismo 7) no Brasil e envia notificação push no celular quando o preço atingir o valor definido. Deve ter dois níveis de alerta: o normal e o especial, para super promoções temporárias (relâmpago).

Roda de graça no GitHub Actions, sem servidor próprio. Código em Python.

## Contexto de preços (referência do usuário)

- Menor preço já visto: R$ 2.799 com cupom MELIMAIS200 no Mercado Livre (Meli+).
- Amazon: R$ 4.029 a R$ 4.259 em até 21x sem juros.
- Faixa comum em lojas: R$ 4.099 a R$ 4.600.
- Black Friday 2026 é em 27/11/2026. Buscar até 30/11/2026.
- O usuário quer muitas parcelas sem juros (12x ou mais).

## Arquitetura

```
ps5-monitor/
  config.yaml            regras de alerta e fontes
  monitor.py             ponto de entrada
  sources/               um módulo por fonte de preço
    promobit.py
    pelando.py
    zoom.py
    (outros, se viável)
  notifier.py            envio de notificações
  storage.py             leitura e escrita do histórico
  data/history.json      histórico de preços e alertas já enviados
  tests/                 testes com HTML/RSS de exemplo salvo
  .github/workflows/monitor.yml
  requirements.txt
  README.md
```

## Fontes de preço

Amazon e Mercado Livre bloqueiam scraping simples. **Não insistir neles como fonte principal.** Priorizar sites que já registram promoções, inclusive as relâmpago:

1. Promobit (RSS ou página de busca de ofertas).
2. Pelando (feed ou busca).
3. Zoom e Buscapé (página do produto com menor preço).
4. Opcional: leitura direta de lojas que permitirem, cada uma em módulo separado.

Cada fonte devolve uma lista de ofertas com estes campos: `loja`, `titulo`, `preco_total`, `parcelas`, `valor_parcela`, `sem_juros` (bool), `cupom`, `link`, `fonte`, `coletado_em`.

Se uma fonte falhar (bloqueio, mudança de HTML, timeout), registrar o erro no log e seguir com as outras. Uma fonte quebrada nunca pode derrubar a execução inteira. Se uma fonte falhar em 6 execuções seguidas, enviar um aviso de manutenção uma única vez.

## Filtros de qualidade

Só considerar a oferta se:

- O título indicar **Edição Digital** e **Astro Bot** (aceitar variações como "Digital", "Slim Digital", "Pacote Astro Bot").
- Rejeitar anúncios de console com disco, só de controle, jogos avulsos, usado, "open box", acessórios e anúncios com "+ 10 jogos" de vendedores desconhecidos.
- Rejeitar preço absurdamente baixo (abaixo de R$ 1.500), que costuma ser golpe ou erro de leitura.
- Normalizar preços para número (R$ 4.029,00 vira 4029.00).

## Regras de alerta (config.yaml)

O usuário deve poder editar tudo no `config.yaml`, sem mexer no código. Exemplo de formato:

```yaml
produto:
  nome: "PS5 Slim Digital + Astro Bot"
  palavras_obrigatorias: ["digital", "astro bot"]
  palavras_proibidas: ["usado", "open box", "controle", "disco"]

alerta_normal:
  # preço máximo por faixa de horário (horário de Fortaleza)
  faixas:
    - { das: "00:00", ate: "23:59", preco_max: 4000 }
  exigir_sem_juros: false
  parcelas_minimas: 1

alerta_especial:
  preco_max: 3200            # super promoção
  queda_percentual: 20       # ou queda de 20% sobre a média recente
  prioridade: urgente
  # relâmpago: se a oferta aparecer nova e tiver desconto grande,
  # avisar na hora mesmo que seja de fonte única
  repetir_a_cada_minutos: 30 # reenvia enquanto a oferta continuar ativa

anti_spam:
  nao_repetir_mesma_oferta_por_minutos: 180
  avisar_so_se_preco_cair_mais: 50   # reais, para reenviar a mesma oferta

periodo:
  inicio: "2026-11-19"
  fim: "2026-11-30"

fuso_horario: "America/Fortaleza"
```

Lógica esperada:

- Oferta que bate o **alerta normal**: notificação de prioridade padrão.
- Oferta que bate o **alerta especial**: notificação de prioridade urgente, com título chamativo, e reenvio enquanto continuar ativa.
- Se o preço for o **menor já visto** no histórico, destacar isso na mensagem.
- Não enviar a mesma oferta repetidamente (usar o histórico e as regras de anti_spam).
- Fora do período configurado, o script termina sem buscar nada.

## Notificações

Usar **ntfy.sh** como padrão (simples, sem criar bot): `POST https://ntfy.sh/<topico>` com os cabeçalhos `Title`, `Priority` (3 para normal, 5 para especial), `Tags` e `Click` (link da oferta). O tópico fica em um secret do GitHub (`NTFY_TOPIC`), com nome longo e difícil de adivinhar.

Deixar o `notifier.py` com uma interface única para que seja fácil trocar por Telegram depois (`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` como secrets). Implementar Telegram como opção, ativada pelo `config.yaml`.

Formato da mensagem:

```
PS5 Digital + Astro Bot: R$ 3.899
12x de R$ 324,92 sem juros
Loja: Amazon | Cupom: nenhum
Menor preço já visto!
(link clicável)
```

## GitHub Actions

Arquivo `.github/workflows/monitor.yml`:

- Gatilhos: `schedule` com cron a cada 10 minutos (`*/10 * * * *`, lembrando que o GitHub pode atrasar) e `workflow_dispatch` para rodar manualmente.
- Cache do pip para ser rápido.
- Rodar `python monitor.py`.
- Ao final, commitar `data/history.json` se mudou, usando o `GITHUB_TOKEN`, com mensagem `chore: atualiza histórico [skip ci]`.
- `permissions: contents: write`.
- `concurrency` para impedir duas execuções ao mesmo tempo.
- Observação para o README: repositórios públicos têm minutos grátis ilimitados no Actions. Em repositório privado há limite mensal, então avaliar o intervalo.

## Requisitos técnicos

- Python 3.11 ou superior.
- Dependências leves: `requests`, `beautifulsoup4`, `feedparser`, `pyyaml`, `pytest`.
- User-Agent realista, timeout de 15 segundos, até 2 tentativas por fonte e pausa curta entre requisições.
- Respeitar os termos e o robots.txt dos sites, sem tentar burlar bloqueios nem usar proxies.
- Logs claros no console, para ler no GitHub Actions.
- Nunca colocar secrets no código nem no histórico.
- Modo `--dry-run` que busca e imprime o que enviaria, sem notificar e sem gravar histórico.
- Modo `--test-notify` que manda uma notificação de teste.

## Testes

- Testes unitários com `pytest` para: parser de cada fonte (usando HTML ou RSS de exemplo salvo em `tests/fixtures/`), filtro de qualidade, regras de alerta normal e especial, anti-spam e normalização de preço.
- Pelo menos um teste para cada regra do `config.yaml`.

## Ordem de construção sugerida

1. Estrutura do projeto, `config.yaml`, `requirements.txt` e `.gitignore`.
2. `storage.py` e modelo de oferta.
3. Filtros de qualidade e motor de regras (com testes).
4. Fonte Promobit, depois Pelando, depois Zoom (cada uma com testes e fixtures).
5. `notifier.py` com ntfy, depois Telegram.
6. `monitor.py` com `--dry-run` e `--test-notify`.
7. Workflow do GitHub Actions.
8. README com passo a passo.

## README deve explicar

- Como criar o repositório e subir o projeto.
- Como instalar o app ntfy no celular e escolher o tópico.
- Como cadastrar os secrets no GitHub (Settings, Secrets and variables, Actions).
- Como editar o `config.yaml` (preço de alerta por faixa de horário e alerta especial).
- Como rodar localmente em modo `--dry-run`.
- Como disparar o workflow manualmente e ler os logs.
- Como pausar ou encerrar o monitoramento.
- Limitações conhecidas: intervalo mínimo e atrasos do GitHub Actions, fontes que podem mudar de HTML, promoções relâmpago muito curtas ainda podem passar.

## Critérios de pronto

- `pytest` passando.
- `python monitor.py --dry-run` mostra ofertas reais e a decisão de alerta para cada uma.
- `python monitor.py --test-notify` chega no celular.
- Workflow roda manualmente com sucesso no GitHub.
- Trocar o valor no `config.yaml` muda o comportamento sem alterar código.
