"""Alertas da VM por Telegram e/ou e-mail (so avisa; nao altera nada e nao manda ordem).

    QUANT_ALERT_ENV=/etc/quant/alert.env  python -m quant.alerts      (chamado a cada minuto por quant-alert.timer)

Le o estado do runner, o systemd, o relatorio do selfcheck e o historico de trades, compara com a ultima execucao
(``alerts_state.json``) e avisa so quando algo MUDA: runner caiu/voltou, trava de risco, kill-switch, selfcheck que
passou a falhar, trade novo fechado. O segredo (token do bot, senha SMTP) fica no arquivo de ambiente, modo 640
root:quant, que VOCE grava; nada daqui o le de volta nem o mostra.

    QUANT_ALERT_TELEGRAM_TOKEN / QUANT_ALERT_TELEGRAM_CHAT           (bot do @BotFather + seu chat id)
    QUANT_ALERT_SMTP_HOST / _PORT / _USER / _PASS / _FROM / _TO      (opcional; STARTTLS)
"""
from __future__ import annotations

import csv
import json
import os
import smtplib
import subprocess
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

NAME = "quant@vm"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_env(path: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def count_trades(path: Path) -> int:
    try:
        return max(sum(1 for _ in csv.reader(path.read_text().splitlines())) - 1, 0)
    except OSError:
        return 0


def last_trades(path: Path, n: int) -> list[dict]:
    try:
        rows = list(csv.DictReader(path.read_text().splitlines()))
    except OSError:
        return []
    return rows[-n:] if n > 0 else []


def snapshot(*, run=None, state_path: Path, selfcheck_path: Path, kill_file: Path, trades_path: Path) -> dict:
    """Foto do que importa agora; ``run`` injeta o systemctl nos testes."""
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip())
    state = _read_json(state_path) or {}
    sc = _read_json(selfcheck_path)
    return {"runner": run(["systemctl", "is-active", "quant-live"]) or "desconhecido",
            "kill": kill_file.exists(),
            "halted": bool((state.get("risk") or {}).get("halted")),
            "halt_reason": (state.get("risk") or {}).get("reason", ""),
            "selfcheck_ok": None if sc is None else bool(sc.get("ok")),
            "n_trades": count_trades(trades_path)}


def diff_events(snap: dict, prev: dict | None, new_trades: list[dict] | None = None) -> list[str]:
    """Mensagens para o que mudou desde ``prev``. Na primeira execucao (prev=None) nao avisa nada: so registra."""
    if prev is None:
        return []
    ev = []
    if snap["runner"] != prev.get("runner"):
        if snap["runner"] == "active":
            ev.append("Runner ligou (quant-live ativo).")
        elif snap["runner"] == "failed":
            ev.append("RUNNER FALHOU (quant-live em estado failed). Veja o log no painel.")
        else:
            ev.append(f"Runner parou (estado: {snap['runner']}).")
    if snap["kill"] and not prev.get("kill"):
        ev.append("KILL-SWITCH acionado: posição fechada e runner parado.")
    if snap["halted"] and not prev.get("halted"):
        ev.append(f"TRAVA DE RISCO: {snap['halt_reason'] or 'sem motivo registrado'}.")
    if snap["selfcheck_ok"] is False and prev.get("selfcheck_ok") is not False:
        ev.append("Autoverificação da VM FALHOU (testes ou saúde). Veja o cartão no painel.")
    if snap["selfcheck_ok"] and prev.get("selfcheck_ok") is False:
        ev.append("Autoverificação da VM voltou ao normal.")
    for t in new_trades or []:
        side = "long" if str(t.get("side")) == "1" else "short"
        ev.append(f"Trade fechado ({t.get('origem', '')}): {side} {t.get('entrada')} → {t.get('saida')}, "
                  f"PnL {t.get('pnl')} ({t.get('motivo', '')}).")
    return ev


def send_telegram(token: str, chat: str, text: str, *, opener=urllib.request.urlopen) -> None:
    data = urllib.parse.urlencode({"chat_id": chat, "text": f"[{NAME}] {text}"}).encode()
    opener(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=10).read()


def send_email(cfg: dict, text: str, *, smtp=smtplib.SMTP) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"] = f"[{NAME}] {text[:60]}", cfg["QUANT_ALERT_SMTP_FROM"]
    msg["To"] = cfg["QUANT_ALERT_SMTP_TO"]
    msg.set_content(text)
    with smtp(cfg["QUANT_ALERT_SMTP_HOST"], int(cfg.get("QUANT_ALERT_SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if cfg.get("QUANT_ALERT_SMTP_USER"):
            s.login(cfg["QUANT_ALERT_SMTP_USER"], cfg.get("QUANT_ALERT_SMTP_PASS", ""))
        s.send_message(msg)


def channels(cfg: dict) -> list[str]:
    out = []
    if cfg.get("QUANT_ALERT_TELEGRAM_TOKEN") and cfg.get("QUANT_ALERT_TELEGRAM_CHAT"):
        out.append("telegram")
    if all(cfg.get(k) for k in ("QUANT_ALERT_SMTP_HOST", "QUANT_ALERT_SMTP_FROM", "QUANT_ALERT_SMTP_TO")):
        out.append("email")
    return out


def deliver(cfg: dict, text: str, *, tg=None, mail=None) -> list[str]:
    """Manda por todos os canais configurados; um canal que falha nao impede os outros. Devolve os que deram certo."""
    tg, mail = tg or send_telegram, mail or send_email  # resolvido na chamada (testes trocam as funcoes do modulo)
    ok = []
    for ch in channels(cfg):
        try:
            if ch == "telegram":
                tg(cfg["QUANT_ALERT_TELEGRAM_TOKEN"], cfg["QUANT_ALERT_TELEGRAM_CHAT"], text)
            else:
                mail(cfg, text)
            ok.append(ch)
        except Exception as e:  # noqa: BLE001 - alerta nunca derruba o watcher; o erro vai pro journal sem o segredo
            print(f"alerta por {ch} falhou: {type(e).__name__}", flush=True)
    return ok


def run_once(env_path: Path, state_file: Path, *, snap: dict, trades_path: Path, deliver_fn=deliver) -> list[str]:
    prev = _read_json(state_file)
    new_trades = []
    if prev is not None and snap["n_trades"] > prev.get("n_trades", 0):
        new_trades = last_trades(trades_path, snap["n_trades"] - prev.get("n_trades", 0))
    events = diff_events(snap, prev, new_trades)
    cfg = load_env(env_path)
    sent = []
    for e in events:
        print(f"evento: {e}", flush=True)
        if deliver_fn(cfg, e):
            sent.append(e)
    delivered_all = len(sent) == len(events)
    # se um evento nao foi entregue (sem canal ou rede fora), NAO avanca o estado: tenta de novo no proximo minuto
    if delivered_all or not channels(cfg):
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap))
        tmp.replace(state_file)
    return events


def main() -> int:
    env = os.environ.get
    snap = snapshot(state_path=Path(env("QUANT_STATE", "live_state.json")),
                    selfcheck_path=Path(env("QUANT_SELFCHECK", "selfcheck.json")),
                    kill_file=Path(env("QUANT_KILL_FILE", "KILL")),
                    trades_path=Path(env("QUANT_TRADES_LOG", "trades.csv")))
    run_once(Path(env("QUANT_ALERT_ENV", "/etc/quant/alert.env")), Path(env("QUANT_ALERT_STATE", "alerts_state.json")),
             snap=snap, trades_path=Path(env("QUANT_TRADES_LOG", "trades.csv")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
