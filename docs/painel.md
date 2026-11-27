# Painel de controle

SPA em Angular ([`web/`](../web/README.md)) servida pelo backend Python (`quant.control`, só em `127.0.0.1:8765`),
atrás do nginx com HTTPS em `/controle/`.

## Telas

| Grupo | Tela | Para quê |
|---|---|---|
| Acompanhar | Visão geral | estado, indicadores principais e tabela de ativos |
| | Ao vivo | o que o robô e a IA estão vendo agora |
| | Observatório | conta, serviços e problemas detectados |
| | Trades | operações fechadas, curva e CSV |
| Agir | Operar | ligar, parar e reiniciar o robô, parâmetros, kill-switch |
| | Boleta | comprar, vender, colocar stop e fechar à mão (demo) |
| | IA | ligar o agente, postura, limites e decisões |
| Analisar | Pesquisa | estudos do repositório |
| | Carteira | paper da carteira diária |
| Sistema | Saúde | autoverificação e serviços |
| | Gestão | publicar e reverter código, alertas |
| Conta | Minha conta, Usuários | senha, 2FA, sessões; usuários e auditoria (admin) |

## Papéis

| Papel | Pode |
|---|---|
| `leitor` | ver |
| `operador` | robô, boleta, parâmetros, kill-switch, ligar a IA, autoverificação, alerta de teste |
| `admin` | tudo, incluindo publicar, reverter, destravar risco, configurar a IA e gerir usuários |

Rota nova sem regra explícita exige `admin`.

## API

Leitura (`GET`):

| Rota | Conteúdo |
|---|---|
| `/api/status` | estado do robô (`?asset=`) |
| `/api/live`, `/api/flow`, `/api/research` | ao vivo, fluxo de um ativo, estudos |
| `/api/metrics` | retrato da conta |
| `/api/trades`, `/api/trades.csv` | operações |
| `/api/agent` | estado e decisões da IA |
| `/api/markets`, `/api/settings`, `/api/order` | catálogo, parâmetros, resultado da boleta |
| `/api/session`, `/api/sessions`, `/api/users`, `/api/audit` | contas |

Ações (`POST`, sempre com o cabeçalho `X-Quant-Control: 1`):

| Rota | Efeito |
|---|---|
| `/api/runner/<ação>` | ligar, parar, reiniciar |
| `/api/settings` | salva parâmetros |
| `/api/kill`, `/api/risk/reset` | kill-switch, destravar risco |
| `/api/order` | pedido da boleta |
| `/api/agent/toggle`, `/config`, `/run` | IA |
| `/api/selfcheck/run`, `/api/alerts/test` | verificação e alerta |
| `/api/deploy/run`, `/api/deploy/rollback` | publicar, reverter |
| `/api/setup`, `/api/login`, `/api/logout`, `/api/password`, `/api/2fa/*`, `/api/sessions/*`, `/api/users*` | contas |

## Segurança

- Senhas com PBKDF2; cookie `HttpOnly`, `Secure`, `SameSite=Strict`, guardado no servidor só como hash.
- 2FA por aplicativo autenticador, opcional; bloqueio crescente por IP; auditoria em `audit.log`.
- Cabeçalho próprio contra CSRF e CSP sem scripts inline.
- O primeiro acesso cria o administrador e a rota fecha.
- Perdeu o acesso: na VM, `sudo deploy/recuperar-acesso.sh senha USUARIO`.

## Desenvolvimento

```bash
cd web
npm ci
npm start        # proxy de /api para o backend local
npm test -- --watch=false
npm run build
```
