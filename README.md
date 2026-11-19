# Monitor de Ofertas: PS5 Slim Digital

Monitora o preço do **PlayStation 5 Slim Edição Digital**, sozinho ou em pacote com jogos, e manda
uma notificação no celular quando o preço cai abaixo do limite que você definiu. Roda de graça no
GitHub Actions a cada 10 minutos, sem servidor.

- **Alerta normal**: preço abaixo do limite da faixa de horário (prioridade padrão).
- **Alerta especial**: super promoção ou queda forte sobre a média recente (prioridade urgente, reenviado
  a cada 30 min enquanto a oferta continuar ativa).
- Destaca quando é o **menor preço já visto**.

Fontes: **Promobit** e **Pelando** (sites de promoções), **Zoom** e **Buscapé** (comparadores de preço) e
**KaBuM** (loja, inclusive ofertas relâmpago). Amazon, Mercado Livre, Magazine Luiza e Casas Bahia não são
consultados diretamente, porque bloqueiam robôs; as promoções deles aparecem no Promobit, no Pelando e nos
comparadores.

O **Pelando bloqueia os servidores do GitHub** (HTTP 403). Rodando no seu computador
(`python monitor.py`) ele funciona. No GitHub ele aparece como "bloqueou o acesso" e as outras fontes seguem.

Para incluir uma fonte nova: crie `sources/<nome>.py` com `NOME`, `buscar()` e `parse()`, registre em
`sources/__init__.py`, salve um HTML de exemplo em `tests/fixtures/` com um teste, e ative em `config.yaml`.

---

## 1. Criar o repositório e subir o projeto

1. No GitHub, crie um repositório (público é o recomendado; veja a seção *Limitações*).
2. No computador:
   ```bash
   git clone https://github.com/<seu-usuario>/<repo>.git
   cd <repo>
   # copie os arquivos do projeto para cá, se ainda não estiverem
   git add .
   git commit -m "Monitor PS5"
   git push
   ```

## 2. Instalar o ntfy no celular e escolher o tópico

1. Instale o app **ntfy** ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) /
   [iPhone](https://apps.apple.com/app/ntfy/id1625396347)).
2. Invente um **nome de tópico longo e difícil de adivinhar**. Qualquer pessoa que souber o nome pode ler
   as mensagens. Exemplo: `ps5-alerta-7f3k9q2xw8m4`.
   Para gerar um nome aleatório: `python -c "import secrets; print('ps5-' + secrets.token_hex(8))"`
3. No app, toque em **+** e assine esse tópico (servidor `ntfy.sh`).
4. Para o alerta especial tocar mesmo no modo silencioso, abra o tópico no app, entre nas configurações de
   notificação e permita que a prioridade "máxima/urgente" ignore o *Não perturbe*.

## 3. Cadastrar os secrets no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Obrigatório | Valor |
|---|---|---|
| `NTFY_TOPIC` | sim (canal ntfy) | o nome do tópico do passo 2 |
| `TELEGRAM_BOT_TOKEN` | só se usar Telegram | token do bot criado no @BotFather |
| `TELEGRAM_CHAT_ID` | só se usar Telegram | id do seu chat (ex.: pelo @userinfobot) |

Os secrets nunca ficam no código. Para usar o Telegram no lugar do ntfy, mude `notificacao.canal` para
`telegram` no `config.yaml`.

## 4. Editar o `config.yaml`

Tudo se ajusta no `config.yaml`, sem mexer no código. Depois de editar, faça commit e push. A mudança vale
a partir da próxima execução.

**Preço de alerta por faixa de horário** (horário de Fortaleza):
```yaml
alerta_normal:
  faixas:
    - { das: "08:00", ate: "17:59", preco_max: 3900 }
    - { das: "18:00", ate: "07:59", preco_max: 4100 }   # faixa que passa da meia-noite é aceita
  exigir_sem_juros: false     # true = só avisa se for parcelado sem juros
  parcelas_minimas: 10        # só avisa se der para parcelar em 10x ou mais
  aceitar_parcelamento_nao_informado: true
```
Vale a primeira faixa que contém o horário atual. Promobit e Pelando quase nunca informam o parcelamento.
Com `aceitar_parcelamento_nao_informado: true`, essas ofertas avisam mesmo assim (a mensagem diz
"parcelamento não informado"). Com `false`, só passam ofertas que informam 10x ou mais. O alerta especial
ignora as exigências de parcelamento: um preço de super promoção avisa mesmo à vista.

**Alerta especial (super promoção / relâmpago):**
```yaml
alerta_especial:
  preco_max: 3700            # qualquer oferta até esse valor é especial
  queda_percentual: 20       # ou 20% abaixo da média dos últimos 7 dias
  janela_media_dias: 7
  prioridade: urgente        # minima, baixa, normal, alta ou urgente
  repetir_a_cada_minutos: 30
```

**Anti-spam:** a mesma oferta (mesmo link) não é reenviada antes de `nao_repetir_mesma_oferta_por_minutos`,
a não ser que o preço caia mais de `avisar_so_se_preco_cair_mais` reais.

**Filtro do produto:** `palavras_obrigatorias` (todas precisam estar no título), `palavras_proibidas`
(nenhuma pode estar no título; "sem disco" é aceito) e `preco_minimo_valido` (abaixo disso é golpe ou erro).
Kits com "+ 3 jogos" ou mais são sempre descartados.

**Fontes:** cada uma pode ser desligada com `ativo: false`. `idade_maxima_horas` descarta posts antigos do
Promobit e do Pelando.

## 5. Rodar localmente

Requer Python 3.11 ou superior.
```bash
pip install -r requirements.txt
python monitor.py --dry-run        # busca nos sites e mostra a decisão de cada oferta, sem notificar nem gravar
pytest                             # testes
```
Para testar a notificação no celular:
```bash
# Linux/macOS
NTFY_TOPIC=seu-topico python monitor.py --test-notify
# Windows PowerShell
$env:NTFY_TOPIC="seu-topico"; python monitor.py --test-notify
```

## 6. Disparar o workflow manualmente e ler os logs

1. Aba **Actions** → workflow **Monitor PS5** → **Run workflow**.
2. Clique na execução e depois em **monitor → Rodar monitor** para ver o log: o que cada fonte retornou, o
   que foi descartado (e por quê) e a decisão de alerta (`NORMAL`/`ESPECIAL`/`NENHUM`, `ENVIAR`/`segurar`).
3. Se o histórico mudou, o próprio workflow faz um commit `chore: atualiza histórico [skip ci]`.

Se uma fonte falhar 6 vezes seguidas (bloqueio ou mudança no site), chega **um único** aviso de manutenção.
As outras fontes continuam funcionando normalmente.

## 7. Página web com as ofertas

Endereço: **`https://<seu-usuario>.github.io/<repo>/`**. A página mostra:

- o status de cada fonte na última verificação;
- a melhor oferta atual, o menor preço já visto e os limites de alerta;
- as ofertas encontradas, com a decisão (super promoção, dentro ou acima do limite);
- os alertas já enviados;
- todas as ofertas vistas nos últimos 30 dias;
- os anúncios descartados pelo filtro, com o motivo.

Ela lê o `data/history.json` direto do repositório e se atualiza sozinha a cada 2 minutos.

Para ativar (já está feito neste repositório): **Settings → Pages → Build and deployment → Source: Deploy
from a branch → Branch: `main`, pasta `/docs` → Save**. A página é pública, como o próprio repositório.
Ela tem `noindex` para não aparecer no Google.

## 8. Rodar também no seu computador (cobre o Pelando)

O Pelando bloqueia o GitHub, mas aceita o seu computador. O script `scripts/rodar_local.py` roda o monitor
no PC e publica o histórico no mesmo repositório, então página e anti-spam continuam únicos. No Windows:

1. Faça um **clone separado** só para isso (o script descarta mudanças locais a cada execução):
   ```bash
   git clone https://github.com/<seu-usuario>/<repo>.git %USERPROFILE%\ps5vem-runner
   echo dedicado > %USERPROFILE%\ps5vem-runner\.runner
   ```
2. Salve o tópico do ntfy fora do repositório, em `%LOCALAPPDATA%\ps5vem\ntfy_topic.txt` (só o nome do tópico).
3. Crie a tarefa no PowerShell (a cada 10 min, sem abrir janela, até 01/12):
   ```powershell
   $py = (Get-Command pythonw).Source
   $acao = New-ScheduledTaskAction -Execute $py -Argument "`"$env:USERPROFILE\ps5vem-runner\scripts\rodar_local.py`"" -WorkingDirectory "$env:USERPROFILE\ps5vem-runner"
   $gat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ((Get-Date "2026-12-01") - (Get-Date))
   $cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
   Register-ScheduledTask -TaskName "Monitor PS5" -Action $acao -Trigger $gat -Settings $cfg
   ```
- **Log:** `%LOCALAPPDATA%\ps5vem\monitor-local.log`.
- **Pausar:** abra o Agendador de Tarefas e desabilite "Monitor PS5". **Remover:** `Unregister-ScheduledTask -TaskName "Monitor PS5"`.
- Só roda com o PC ligado e acordado. Com o PC desligado, o GitHub Actions continua com as outras fontes.

## 9. Busca 24h no GitHub: a "corrente"

O agendamento próprio do GitHub (`schedule`) pode demorar horas para começar ou pular execuções. Por isso o
workflow funciona como uma **corrente**: cada execução busca, espera ~10 minutos e dispara a próxima, usando
só a permissão interna do workflow (sem token). Para iniciar, basta rodar o workflow uma vez manualmente
(Actions → Monitor PS5 → Run workflow).

- **Não duplica:** se já houver uma execução na fila, a corrente não dispara outra.
- **Para sozinha** depois do fim do `periodo` do `config.yaml`.
- **Reinício automático:** se a corrente quebrar, o script do computador (seção 8) percebe que não houve
  execução há mais de 25 minutos e dispara uma nova.
- **Interromper:** Actions → Monitor PS5 → menu **⋯** → **Disable workflow**.
- Cada execução ocupa uma máquina do GitHub por ~11 minutos (a maior parte esperando). Em repositório
  público é gratuito; em privado consumiria a cota rapidamente.

**Alternativa opcional, cron-job.org:** um serviço gratuito pode disparar o workflow a cada 10 minutos,
no lugar da corrente:

1. No GitHub: **Settings (do seu perfil) → Developer settings → Personal access tokens → Fine-grained tokens →
   Generate new token**. Em *Repository access*, escolha **Only select repositories** e marque este repositório.
   Em *Permissions → Repository permissions*, dê **Actions: Read and write**. Defina a validade até 01/12.
2. No cron-job.org, crie um cronjob:
   - URL: `https://api.github.com/repos/<seu-usuario>/<repo>/actions/workflows/monitor.yml/dispatches`
   - Agendamento: a cada 10 minutos.
   - Em *Advanced*: método **POST**; cabeçalhos `Authorization: Bearer <seu token>`,
     `Accept: application/vnd.github+json` e `Content-Type: application/json`; corpo `{"ref":"main"}`.
3. Salve e use **Test run**. Deve aparecer uma execução nova em Actions (resposta HTTP 204 = sucesso).

O token fica só no cron-job.org, nunca no repositório. Para parar, desative o cronjob ou apague o token.

## 10. Pausar ou encerrar

- **Pausar:** Actions → Monitor PS5 → menu **⋯** → **Disable workflow** (para reativar, **Enable workflow**).
- **Encerrar automaticamente:** fora do `periodo` do `config.yaml` (padrão: 19/11 a 30/11/2026), o script
  termina sem buscar nada. Depois do fim do período, desative o workflow para não gastar execuções à toa.
- **Silenciar só um canal:** apague o secret ou cancele a assinatura do tópico no app.

## Limitações conhecidas

- **Intervalo e atrasos do GitHub Actions:** o mínimo é 5 minutos, e o agendamento costuma atrasar de 5 a
  20 minutos (às vezes pula execuções) em horários de pico. Promoções relâmpago muito curtas ainda podem
  passar.
- **Minutos grátis:** repositórios **públicos** têm minutos ilimitados no Actions. Em repositório
  **privado** há uma cota mensal (2.000 min no plano Free). Uma execução leva cerca de 1 min, e a cada
  10 min isso dá ~4.300 min/mês, acima da cota. Em repositório privado, use `*/30 * * * *` ou deixe público
  (o tópico do ntfy continua secreto, porque está nos secrets).
- **Os sites mudam de HTML:** os parsers leem os dados estruturados das páginas (`__NEXT_DATA__` e as props
  do Astro). Se o site mudar, a fonte passa a falhar, o log mostra o erro e você recebe o aviso de manutenção.
- **Ofertas encerradas:** o Promobit não informa na listagem se a oferta acabou. Por isso posts com mais de
  48 h são ignorados, mas uma oferta recém-encerrada (ou válida só em lojas físicas) ainda pode gerar alerta.
  Confira o link antes de comprar.
- **Parcelamento:** só o Zoom informa parcelas e juros de forma estruturada.
- **robots.txt:** o monitor respeita o robots.txt e não tenta contornar bloqueios (403/429/captcha). Uma
  fonte bloqueada simplesmente fica de fora.

## Estrutura

```
config.yaml           regras de alerta e fontes (edite aqui)
monitor.py            ponto de entrada (--dry-run, --test-notify)
sources/              uma fonte por módulo (promobit, pelando, zoom, buscape, kabum)
filters.py            normalização de preço e filtro de qualidade
rules.py              alerta normal/especial, faixas de horário, anti-spam, período
notifier.py           ntfy e Telegram com interface única
storage.py            histórico em data/history.json
http_client.py        requisições (User-Agent, timeout 15 s, 2 tentativas, robots.txt)
tests/                pytest + fixtures com HTML real das fontes
docs/index.html       página web com as ofertas (GitHub Pages)
scripts/rodar_local.py roda o monitor no seu computador (Agendador do Windows)
.github/workflows/    agendamento no GitHub Actions
```
