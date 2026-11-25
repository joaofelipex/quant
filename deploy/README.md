# Deploy na VM

> Estes arquivos têm testes de estrutura (`tests/test_deploy.py`), mas **nunca foram executados numa VM**: rode
> `nginx -t` e `systemd-analyze verify /etc/systemd/system/quant-*.service` antes de ligar qualquer coisa.

| Fase | O que sobe | Quando |
|---|---|---|
| 1. Paper da carteira + painel | `quant-portfolio.timer`, nginx | já pode; não usa chaves nem manda ordens |
| 2. Runner na testnet | `quant-live.service` com `QUANT_MODE=testnet` | depois da checagem de fumaça (`docs/roteiro_testnet.md`) |
| 3. Conta real | nada | só com estratégia aprovada pela regra do README |

**Depois de cada fase, rode a verificação na VM:** `sudo bash deploy/verificar.sh` (só consulta; confere DNS, timer, estado,
permissões, `nginx -t`, HTTP 301, HTTPS 401, certificado e, se instalado, o runner).

## 0. Base (uma vez)

```bash
useradd --system --home /opt/quant --shell /usr/sbin/nologin quant
git clone git@github.com:joaofelipex/quant.git /opt/quant && cd /opt/quant
python3 -m venv .venv && .venv/bin/pip install -e ".[live]"
chown -R quant:quant /opt/quant
install -d -o quant -g www-data -m 0755 /var/www/quant      # onde o painel é escrito (nginx só lê)
install -d -m 0755 /var/www/certbot                          # desafio do certbot
```

O diretório de estado `/var/lib/quant` é criado pelo systemd (`StateDirectory=quant`).

## 1. Paper da carteira (fase 1)

```bash
install -m 0600 deploy/quant-portfolio.env.example /etc/quant-portfolio.env   # sem chaves de corretora
cp deploy/quant-portfolio.service deploy/quant-portfolio.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start quant-portfolio.service && journalctl -u quant-portfolio -n 30   # disparo manual de teste
systemctl enable --now quant-portfolio.timer && systemctl list-timers quant-portfolio.timer
```

O serviço **nunca lê** `/etc/quant-live.env` (onde ficam as chaves) e roda com privilégio mínimo.

**Região da VM:** o paper usa só dados públicos. Os preços vêm de `data-api.binance.vision`, que responde de qualquer região.
A API de futuros (funding) devolve 451 em IPs dos EUA (ex.: Oracle Ashburn): nesse caso o paper roda sem funding e o painel avisa;
o equity ignora o funding (cerca de -1,7% a.a. no estudo). Numa VM em região permitida o funding entra sozinho.

## 2. Painel com HTTPS (a senha nunca trafega em HTTP)

Ordem obrigatória: a porta 80 só pode servir o desafio do certbot até o certificado existir.

```bash
apt install nginx certbot apache2-utils
htpasswd -c /etc/nginx/.htpasswd-quant <usuario>                     # senha só na VM

# passo 1: só o desafio do certbot
cp deploy/nginx-quant-bootstrap.conf /etc/nginx/sites-available/quant.mixco.com.br
ln -s /etc/nginx/sites-available/quant.mixco.com.br /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot certonly --webroot -w /var/www/certbot -d quant.mixco.com.br

# passo 2: painel em HTTPS; a porta 80 só renova e redireciona
cp deploy/nginx-quant.conf /etc/nginx/sites-available/quant.mixco.com.br
nginx -t && systemctl reload nginx
```

Conferência: `curl -I http://quant.mixco.com.br` deve dar **301** (nunca 401 nem o painel);
`curl -u usuario https://quant.mixco.com.br` deve mostrar o painel.

## 3. Runner (fase 2)

### 3a. Sem chaves: paper com dados reais (a partir da VM nos EUA)

Não precisa de nenhuma chave da Binance e **não envia ordens**. O executor é simulado (`PaperExecutor`) e os preços vêm do endpoint
público de dados (`data-api.binance.vision`, spot `ETHUSDT`, sem a base spot-perp de poucos bps). A posição simulada, o stop e o risco
sobrevivem a reinícios do serviço (estado em `/var/lib/quant/live_state.json`).

```bash
sudo install -m 0600 -o root -g root deploy/quant-live.env.example /etc/quant-live.env      # só se ainda não existir
sudo sed -i 's/^QUANT_MODE=.*/QUANT_MODE=paper/; s/^QUANT_TIMEFRAME=.*/QUANT_TIMEFRAME=1m/' /etc/quant-live.env
sudo cp deploy/quant-live.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now quant-live && journalctl -u quant-live -f
```

O que o paper cobre do `docs/roteiro_testnet.md` e o que **só** a exchange cobre:

| Ensaio | No paper sem chaves | Só com a exchange |
|---|---|---|
| A entrada ponta a ponta | sim (stop por software) | stop `STOP_MARKET` no book |
| B processo morre com posição | sim (a posição simulada é restaurada) | stop continua vivo na exchange |
| C/D stop apagado ou disparado pela corretora | não | sim |
| E kill-switch, G perda diária, H dado atrasado | sim | |
| F rede cai | parcial (feed público) | ordens e reconciliação reais |

O paper **não prova** que o executor da Binance funciona: isso continua dependendo da testnet com chaves (3b).

### 3b. Testnet com chaves de teste (opcional, quando você as tiver)

Só depois do paper estável. As chaves **nunca** passam pelo chat nem por `echo`: você as digita num terminal seu, na VM.

| Ambiente de teste | Alcança a partir da VM nos EUA? | `QUANT_TESTNET_KIND` |
|---|---|---|
| Sandbox legado de futuros (`testnet.binancefuture.com`) | **sim** | `testnet` (padrão) |
| Demo Trading (`demo-fapi.binance.com`) | **não** (HTTP 451) | `demo` (só em VM fora dos EUA) |

1. **Crie as chaves de teste** no ambiente escolhido (sem permissão de saque). As do sandbox legado não valem no Demo e vice-versa.
   O sandbox legado foi descontinuado pela Binance em favor do Demo Trading e **pode não aceitar mais cadastros**; se não
   conseguir chaves nele, rode a checagem de fumaca no seu computador com Demo (`docs/roteiro_testnet.md`) e leve o runner
   para uma VM fora dos EUA.
2. **Instale o env e a unit** (a unit só liga depois das chaves):

```bash
sudo install -m 0600 -o root -g root deploy/quant-live.env.example /etc/quant-live.env
sudo sed -i 's/^QUANT_MODE=.*/QUANT_MODE=testnet/; s/^QUANT_TIMEFRAME=.*/QUANT_TIMEFRAME=1m/' /etc/quant-live.env   # 1m: mais sinais
sudo cp deploy/quant-live.service /etc/systemd/system/ && sudo systemctl daemon-reload
```

3. **Grave as chaves** (digitação silenciosa, validação de formato, arquivo com modo 600):
   `sudo bash deploy/definir-chaves.sh`
4. **Checagem de fumaça** (abre e fecha uma posição mínima na testnet; as chaves vão pelo systemd, nunca pela tela):
   `sudo bash deploy/testnet-smoke.sh`. Só avance com tudo `OK`.
5. **Ligue o runner e acompanhe:** `sudo systemctl enable --now quant-live && journalctl -u quant-live -f`

Os dois scripts **recusam** `QUANT_MODE=live`.

**Kill-switch:** `touch /var/lib/quant/KILL` fecha a posição, cancela os stops e **para o serviço de vez**
(`Restart=on-failure`: o processo sai com código 0; e com o arquivo presente o systemd nem inicia o serviço).

**Retomar depois de um kill:** o risco continua travado de propósito (`halted` no estado), para um humano rever.
Pare o serviço, confira a posição na corretora, edite `risk.halted` para `false` em `/var/lib/quant/live_state.json`
(ou apague o arquivo, **só se não houver posição aberta**: com posição e sem estado o runner trava por "posição
órfã"), depois `rm /var/lib/quant/KILL && systemctl start quant-live`.

## 4. Painel de controle (`/controle/`)

Estado ao vivo do runner, ligar/parar/reiniciar, parametros validados e kill-switch, atras do mesmo HTTPS + senha do painel.

```bash
sudo cp deploy/quant-control.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now quant-control
sudo install -m 0644 -o root -g root deploy/50-quant-control.rules /etc/polkit-1/rules.d/    # so quant-live: start/stop/restart
sudo cp deploy/nginx-quant.conf /etc/nginx/sites-available/quant.mixco.com.br && sudo nginx -t && sudo systemctl reload nginx
```

- Parametros salvos pelo painel vao para `/var/lib/quant/runtime.env` (sem segredos, so whitelist validada) e vencem o `/etc/quant-live.env`.
- **Nao** da para ligar `live` nem Polymarket pelo navegador, nem apagar o `KILL`: isso so por edicao na VM.
- Com `KILL` presente o painel recusa ligar/reiniciar (409).

## 5. Gestão da VM pelo painel (histórico, alertas, atualização)

Instalação (uma vez, e de novo se as units mudarem):

```bash
sudo cp deploy/quant-alert.service deploy/quant-alert.timer deploy/quant-deploy.service deploy/quant-rollback.service \
        deploy/quant-live.service deploy/quant-control.service deploy/quant-order.service /etc/systemd/system/
sudo install -m 0644 deploy/50-quant-control.rules /etc/polkit-1/rules.d/
sudo systemctl daemon-reload && sudo systemctl enable --now quant-alert.timer && sudo systemctl restart quant-control
```

**Histórico de trades:** o runner grava cada trade fechado em `/var/lib/quant/trades.csv` (corretora/modo, lado, preços,
PnL, motivo). O painel mostra curva, acerto, pior queda e os últimos trades, e o CSV baixa em `/controle/api/trades.csv`.
O PnL de saída por stop da corretora é uma estimativa (o runner não vê o preço real do fill do gatilho).

**Contas e login do painel:** `/controle/` tem tela de login própria, com usuários, papéis e auditoria:

- **Primeiro acesso:** sem nenhum usuário, o painel mostra a tela "primeiro acesso" e o primeiro a abrir cria o admin (sem token);
  depois a rota fecha. Faça isso **antes** de expor o painel sem o basic auth do nginx.
- **Papéis:** `leitor` só vê; `operador` liga/para o runner, usa a Boleta, o kill-switch e os parâmetros; `admin` também
  atualiza/reverte o código e gere usuários. O servidor confere o papel em cada rota (401 sem sessão, 403 sem papel).
- **Segurança:** senhas com PBKDF2 (nunca em texto); cookie de sessão `HttpOnly`/`Secure`/`SameSite=Strict`, sorteado e guardado
  só como hash no servidor (dá para encerrar sessões, e trocar a senha, mudar o papel ou desativar a conta derruba as sessões);
  2FA opcional por aplicativo autenticador (TOTP; cada código vale uma vez); bloqueio crescente por IP após 5 erros; trilha de
  auditoria em `/var/lib/quant/audit.log` (logins, falhas e ações), visível na aba Usuários.
- **Telas:** *Minha conta* (trocar senha, 2FA, sessões abertas) para todos; *Usuários e auditoria* só para admin.
- **Perdeu o acesso?** Na VM: `sudo deploy/recuperar-acesso.sh senha USUARIO` (cria um admin ou troca a senha) ou `... 2fa USUARIO`.

Depois de confirmar que o login funciona, desligue o basic auth do nginx **só** no `/controle/` (o `/` continua protegido): copie
os blocos `/controle/` de `deploy/nginx-quant.conf` para `/etc/nginx/sites-available/quant.mixco.com.br`, `sudo nginx -t` e
`sudo systemctl reload nginx`.

**Vários ativos:** com `QUANT_ASSETS=BTC,NVDA,AAPL,...` (ou `todos` = os 20 cripto da Binance, ou `tudo` = os 145 do catálogo; escolha
por classe na aba Operar) o `quant-live` roda um runner por ativo no mesmo processo, só na Kalshi demo. O catálogo (`src/quant/live/catalog.json`,
gerado por `scripts/gen_catalog.py`) tem os perpétuos `KX<ID>PERP1` ativos: ações (Nvidia, Apple...), cripto, câmbio, metais, índices e GPU.
Preços: os 20 cripto da Binance usam as barras públicas dela; todos os outros usam as **velas públicas da própria Kalshi**
(1 min e 1 h; 5m/15m são agregados das de 1 min; só se baixa o que falta, 1 chamada por ativo por ciclo). Cada ativo tem
estado próprio (`live_state.<ATIVO>.json`), stop na corretora e limite de perda diária próprio; roda só quando a barra dele fecha,
em paralelo (12 threads), e um erro num ativo repete só aquele. `QUANT_MAX_TOTAL_LOSS` trava as **entradas** de todos quando a soma do
dia chega nele; o kill-switch fecha todos em ~1 s. Tamanho por valor: `QUANT_NOTIONAL` (USD por entrada, padrão 25) vira contratos
inteiros de cada ativo; ativos cujo menor contrato passa de 1,5 x esse valor ficam de fora (com aviso no log). A Visão geral mostra a
tabela de ativos (com filtro); a Boleta pede ativo + valor em USD. Sem `QUANT_ASSETS` tudo funciona como antes (um ativo, `QUANT_QTY`).

**Agente de IA (aba IA):** um agente (Claude, via API da Anthropic) que decide e opera sozinho **só na Kalshi demo**. A cada ciclo
(padrão 10 min) ele recebe só números do sistema (livro de ofertas do universo, retornos e volatilidade dos candidatos, posições, PnL do dia,
limites), responde pela ferramenta `decide` e o **código** valida cada ação antes de executar: valor máximo por entrada, posições abertas,
perda máxima do dia (ao atingir, para de abrir e se desliga), stop obrigatório numa faixa, cooldown por ativo, só comprado (padrão),
kill-switch, só `testnet`, e nunca um ativo que o runner esteja operando. Executa pela mesma rota da Boleta; se uma posição abrir sem
stop, fecha na hora; posição acima do tempo máximo é fechada por regra. Tudo fica em `/var/lib/quant/agent/decisions.jsonl` (e na tela IA).
Ligar/desligar: operador; limites, modelo e universo: admin. A chave da API fica em `/etc/quant/agent.env` (você grava, o painel nunca lê):
`sudo bash /opt/quant/deploy/definir-chave-ia.sh`. Instalação:
`sudo cp deploy/quant-agent.service deploy/quant-agent-agora.service deploy/quant-agent.timer /etc/systemd/system/ && sudo cp deploy/50-quant-control.rules /etc/polkit-1/rules.d/ && sudo systemctl daemon-reload && sudo systemctl enable --now quant-agent.timer`.
Custo: 1 chamada ao modelo por ciclo (aba IA mostra os tokens). Um agente de IA operando **não é prova de vantagem estatística**: acompanhe o PnL
dele contra o do runner e o estudo de fluxo antes de dar mais autonomia.

**Leitura de fluxo (gravador + estudo):** a estratégia hoje olha só o preço (velas). O livro de ofertas da Kalshi só existe "agora" (sem
histórico), então para saber se o desequilíbrio compra/venda ajuda a entrar, é preciso **gravar e medir**. O `quant-flow.timer` tira uma
foto por minuto dos ativos do runner (desequilíbrio em 0,25% e 1% do preço, topo do livro, spread; só leitura pública, sem chave) em
`/var/lib/quant/flow/AAAA-MM-DD.csv`. Depois de alguns dias: `sudo -u quant /opt/quant/.venv/bin/python -m quant.flow study` mostra, por
horizonte (1, 5, 15 min), o poder preditivo (IC, z), o retorno por quintil e o que sobra **depois do spread**. Só se houver sinal
(|z| > 3 e líquido > 0) o desequilíbrio vira filtro de entrada. Instalação:
`sudo cp deploy/quant-flow.service deploy/quant-flow.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now quant-flow.timer`.

**Trava de risco:** a trava por perda do dia (limite por ativo ou `QUANT_MAX_TOTAL_LOSS`) some sozinha na virada do dia UTC; as outras
(kill-switch, posição órfã, falha de stop, lacuna de dados) ficam até decisão sua. Em Operar, admin tem o botão **Destravar risco**
(para o runner, zera a trava e o PnL do dia de todos os ativos e religa; não toca em posições nem stops).

**Boleta manual (Boleta):** comprar, vender, colocar stop e fechar a mão pelo painel, só na Kalshi **demo**. O painel não tem
chave: ele grava um pedido validado e dispara `quant-order.service` (que tem a chave e recusa tudo que não seja `kalshi` +
`testnet`). Abrir/proteger exige o runner parado; fechar e consultar sempre funcionam. Teto de 0,05 por ordem; o KILL bloqueia
novas aberturas. Cada fechamento entra no histórico como `manual`.

**Alertas (Telegram e/ou e-mail):** o `quant-alert.timer` roda a cada minuto e só avisa quando algo MUDA (runner ligou/parou/falhou,
trava de risco, kill-switch, autoverificação, trade novo). O segredo fica num arquivo que **você** grava na VM:

```bash
sudo install -d -m 750 -o root -g quant /etc/quant
sudo install -m 640 -o root -g quant /dev/null /etc/quant/alert.env && sudo nano /etc/quant/alert.env
#   QUANT_ALERT_TELEGRAM_TOKEN=...   (bot do @BotFather)
#   QUANT_ALERT_TELEGRAM_CHAT=...    (seu chat id)
#   opcional e-mail: QUANT_ALERT_SMTP_HOST / _PORT / _USER / _PASS / _FROM / _TO
```

O botão "Enviar alerta de teste" do painel confirma o canal. O painel nunca mostra o token (só o nome do canal).

**Painel Angular:** o front mora em `web/` (ver `web/README.md`). O build vai no pacote como `web-dist/` e o backend o serve de
`/opt/quant/web-dist` (`QUANT_WEB_DIR` na unit). Precisa de Node/npm só no seu computador, nunca na VM.

**Atualizar o código pelo painel:** o painel **não recebe código pela web**. No seu computador, na raiz do repo:
`deploy/enviar-pacote.sh CAMINHO_DA_CHAVE_SSH` (roda o build do Angular, empacota o `HEAD` + `web-dist/` e põe em `/var/lib/quant/inbox/` por SSH). No painel,
"Atualizar código": a VM valida o pacote (sem caminhos suspeitos), roda a suite **numa cópia de staging**, faz backup
(`/var/lib/quant/backups`, guarda 5), aplica e confere que importa; se algo falhar, restaura sozinha. Depois reinicie o
runner para usar o código novo. "Reverter" volta ao último backup. O polkit libera só `start` dessas units e o restart do painel.
