"""Rotas de conta do painel (login, primeiro acesso, 2FA, sessoes, usuarios, auditoria) e a tabela de papeis por rota.

Separado de ``control.py`` para ser testavel sem HTTP: ``handle`` recebe o ``Auth``, o metodo, o caminho e o corpo ja
lido e devolve ``(codigo, json, cookie)``; ``cookie`` e ``None``, ``("set", valor, ttl)`` ou ``("clear",)``.
"""
from __future__ import annotations

from .auth import RANK, ROLES, Auth, AuthError

# papel minimo por rota; "any" = qualquer logado; None = publica. O que nao esta aqui exige admin (falha fechada).
_OPERATOR_POST = ("/api/order", "/api/kill", "/api/settings", "/api/selfcheck/run", "/api/alerts/test")
_ANY_POST = ("/api/password", "/api/2fa/start", "/api/2fa/enable", "/api/2fa/disable", "/api/sessions/revoke",
             "/api/sessions/revoke-others")
_PUBLIC = ("/api/login", "/api/logout", "/api/setup", "/api/session")


def required_role(method: str, path: str) -> str | None:
    if path in _PUBLIC:
        return None
    if method == "GET":
        if path in ("/api/users", "/api/audit"):
            return "admin"
        return "any" if path == "/api/sessions" else "leitor"
    if path in _ANY_POST:
        return "any"
    if path in _OPERATOR_POST or path.startswith("/api/runner/"):
        return "operador"
    return "admin"  # deploy, rollback, usuarios e qualquer rota nova


def allowed(role: str, need: str) -> bool:
    return need == "any" or RANK[role] >= RANK[need]


def _s(body: dict, key: str, limit: int = 256) -> str:
    v = body.get(key, "")
    return v[:limit] if isinstance(v, str) else ""


def handle(auth: Auth, method: str, path: str, sess: dict | None, body: dict, *, ip: str, agent: str = "",
           cookie_header: str | None = None):
    """Trata as rotas de conta. Devolve None se ``path`` nao for de conta (o chamador segue com as outras rotas)."""
    try:
        return _handle(auth, method, path, sess, body, ip, agent, cookie_header)
    except AuthError as e:
        extra = {"codigo": True} if e.need_code else {}
        return e.status, {"ok": False, "erro": str(e), **extra}, None


def _handle(auth, method, path, sess, body, ip, agent, cookie_header):  # noqa: C901 - tabela de rotas
    uid = sess["id"] if sess else ""
    if method == "GET":
        if path == "/api/session":
            return 200, {"user": sess, "setup": auth.needs_setup}, None
        if path == "/api/sessions":
            return 200, {"sessions": auth.list_sessions(uid, sess["sid"])}, None
        if path == "/api/users":
            return 200, {"users": auth.list_users(), "roles": list(ROLES)}, None
        if path == "/api/audit":
            return 200, {"eventos": auth.read_audit(300)}, None
        return None

    if path == "/api/setup":
        u = auth.setup(_s(body, "token"), _s(body, "user", 60), _s(body, "password"), ip)
        token, ttl, _ = auth.login(u["user"], _s(body, "password"), ip, agent=agent)
        return 200, {"ok": True, "user": auth.public(u)}, ("set", token, ttl)
    if path == "/api/login":
        token, ttl, user = auth.login(_s(body, "user", 60), _s(body, "password"), ip, code=_s(body, "code", 12),
                                      remember=bool(body.get("lembrar")), agent=agent)
        return 200, {"ok": True, "user": user}, ("set", token, ttl)
    if path == "/api/logout":
        if sess:
            auth.audit("logout", sess["user"], ip)
        auth.logout(cookie_header)
        return 200, {"ok": True}, ("clear",)
    if sess is None:
        return None

    if path == "/api/password":
        auth.change_password(uid, _s(body, "atual"), _s(body, "nova"))
        auth.audit("senha-trocada", sess["user"], ip)
        return 200, {"ok": True}, ("clear",)  # todas as sessoes dele morreram, inclusive esta
    if path == "/api/2fa/start":
        return 200, {"ok": True, **auth.totp_start(uid)}, None
    if path == "/api/2fa/enable":
        auth.totp_enable(uid, _s(body, "code", 12))
        auth.audit("2fa-ativado", sess["user"], ip)
        return 200, {"ok": True}, None
    if path == "/api/2fa/disable":
        auth.totp_disable(uid, _s(body, "password"))
        auth.audit("2fa-desativado", sess["user"], ip)
        return 200, {"ok": True}, None
    if path == "/api/sessions/revoke":
        ok = auth.revoke_session(uid, _s(body, "id", 64), admin=False)
        return (200 if ok else 404), {"ok": ok, **({} if ok else {"erro": "sessao nao encontrada"})}, None
    if path == "/api/sessions/revoke-others":
        n = auth.revoke_others(uid, sess["sid"])
        auth.audit("sessoes-encerradas", sess["user"], ip, f"{n} outras")
        return 200, {"ok": True, "encerradas": n}, None

    if path == "/api/users":
        u = auth.create_user(_s(body, "user", 60), _s(body, "password"), _s(body, "role", 20) or "leitor")
        auth.audit("usuario-criado", sess["user"], ip, f"{u['user']} ({u['role']})")
        return 200, {"ok": True, "user": u}, None
    if path.startswith("/api/users/"):
        _, _, _, target, verb = (path.split("/") + [""])[:5]
        if verb == "update":
            kw: dict = {}
            if "role" in body:
                kw["role"] = _s(body, "role", 20)
            if "disabled" in body:
                kw["disabled"] = bool(body["disabled"])
            if body.get("reset_2fa"):
                kw["reset_2fa"] = True
            if target == uid and (kw.get("disabled") or ("role" in kw and kw["role"] != sess["role"])):
                raise AuthError("voce nao pode se desativar nem mudar o proprio papel", 409)
            u = auth.update_user(target, **kw)
            auth.audit("usuario-alterado", sess["user"], ip, f"{u['user']}: {sorted(kw)}")
            return 200, {"ok": True, "user": u}, None
        if verb == "password":
            auth.set_user_password(target, _s(body, "password"))
            auth.audit("senha-redefinida", sess["user"], ip, target)
            return 200, {"ok": True}, ("clear",) if target == uid else None
        if verb == "delete":
            if target == uid:
                raise AuthError("voce nao pode apagar a propria conta", 409)
            auth.delete_user(target)
            auth.audit("usuario-apagado", sess["user"], ip, target)
            return 200, {"ok": True}, None
    return None
