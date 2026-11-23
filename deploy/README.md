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
