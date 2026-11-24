# quant · painel de controle (Angular)

SPA em Angular (componentes standalone, signals, rotas com lazy load, sem zone.js). Fala só com a API do `quant.control`
(Python, `127.0.0.1:8765`), que também serve o build. Páginas: Visão geral, Operar, Trades, Carteira, Saúde, Gestão.

```bash
npm ci
npm test            # vitest: formatação, gráficos, banner de estado, serviço da API e renderização das páginas
npm run build       # gera dist/web/browser (arquivos com hash; index.html sem cache)
```

**Desenvolvimento:** rode o backend (`python -m quant.control`, porta 8765) e `npm start`; o dev server faz proxy de `/api` para ele.

**Produção:** `deploy/enviar-pacote.sh` roda o build, empacota o `HEAD` + `web-dist/` e põe na caixa de entrada da VM; o botão
"Atualizar código" do painel testa o pacote e aplica. O backend serve `/opt/quant/web-dist` (`QUANT_WEB_DIR`).

Decisões: rotas por hash (`#/trades`), porque o painel vive em `/controle/` atrás do nginx e assim não precisa de regra de rewrite;
caminhos da API relativos (`api/status`); todo POST leva `X-Quant-Control: 1` (barra CSRF). O backend responde o index com CSP
(`script-src 'self'`), então não use scripts inline nem `eval`.
