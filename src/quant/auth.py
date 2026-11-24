"""Contas do painel: usuarios com papeis, sessoes no servidor, 2FA (TOTP), primeiro acesso e auditoria. So stdlib.

Tudo mora em ``QUANT_AUTH_DIR`` (padrao /var/lib/quant, arquivos 0600): ``users.json`` (hash PBKDF2 das senhas, nunca o
texto), ``sessions.json`` (so o SHA-256 do cookie: roubar o arquivo nao da acesso), ``audit.log`` (uma linha JSON por
evento) e ``setup-token`` (existe so enquanto nao ha nenhum usuario: quem le o arquivo na VM cria o primeiro admin).

Papeis: ``leitor`` (so ve), ``operador`` (liga/para o runner, boleta, kill-switch, parametros) e ``admin`` (tudo, mais
atualizar/reverter codigo e gerir usuarios). Recuperacao se perder o acesso, na VM:
    sudo -u quant /opt/quant/.venv/bin/python -m quant.auth set-password USUARIO     (cria admin ou troca a senha)
    sudo -u quant /opt/quant/.venv/bin/python -m quant.auth reset-2fa USUARIO
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import math
import os
import secrets
import struct
import sys
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

ITERATIONS = 600_000
MIN_PASSWORD = 10
COOKIE = "quant_session"
SESSION_TTL_S = 12 * 3600
REMEMBER_TTL_S = 7 * 24 * 3600
ROLES = ("leitor", "operador", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
AUTH_DIR = Path("/var/lib/quant")
ISSUER = "quant"


class AuthError(ValueError):
    """Pedido recusado (mensagem em portugues). ``status`` = codigo HTTP; ``need_code`` = pede o codigo do 2FA."""

    def __init__(self, msg: str, status: int = 400, need_code: bool = False):
        super().__init__(msg)
        self.status, self.need_code = status, need_code


# ---- senha ------------------------------------------------------------------------------------------------------
def hash_password(password: str, *, salt: bytes | None = None, iterations: int | None = None) -> str:
    iterations = iterations or ITERATIONS
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, want = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(got, base64.b64decode(want))
    except (ValueError, TypeError):
        return False


def check_new_password(pw: str) -> None:
    if len(pw) < MIN_PASSWORD:
        raise AuthError(f"a senha precisa de pelo menos {MIN_PASSWORD} caracteres")
    if len(set(pw)) < 5 or pw.lower() in {"password123", "1234567890", "qwertyuiop", "senha12345"}:
        raise AuthError("senha fraca demais: misture letras, numeros e simbolos")


def check_username(user: str) -> str:
    user = user.strip()
    if not user or len(user) > 40 or not user.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise AuthError("usuario invalido (1 a 40 letras, numeros, . - _)")
    return user


# ---- TOTP (RFC 6238: SHA-1, 6 digitos, 30 s) --------------------------------------------------------------------
def totp_code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 15
    return f"{(struct.unpack('>I', mac[off:off + 4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def totp_uri(user: str, secret: str) -> str:
    return f"otpauth://totp/{ISSUER}:{user}?secret={secret}&issuer={ISSUER}&digits=6&period=30"


class Auth:
    def __init__(self, directory: Path = AUTH_DIR, *, now=time.time):
        self.dir, self.now = Path(directory), now
        self.lock = threading.RLock()
        self.fails: dict[str, list[float]] = {}  # ip -> [falhas seguidas, bloqueado_ate]
        self.mem: dict[str, float] = {}          # sid -> ultimo uso (so memoria)

    @classmethod
    def from_env(cls, env=os.environ.get) -> Auth:
        return cls(Path(env("QUANT_AUTH_DIR", str(AUTH_DIR))))

    # ---- arquivos -----------------------------------------------------------------------------------------------
    def _read(self, name: str, default):
        try:
            return json.loads((self.dir / name).read_text())
        except (OSError, ValueError):
            return default

    def _write(self, name: str, data) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        tmp.replace(self.dir / name)

    def _users(self) -> list[dict]:
        d = self._read("users.json", {"users": []})
        return d["users"] if isinstance(d, dict) and isinstance(d.get("users"), list) else []

    def _save_users(self, users: list[dict]) -> None:
        self._write("users.json", {"users": users})

    def _sessions(self) -> dict:
        d = self._read("sessions.json", {})
        return d if isinstance(d, dict) else {}

    def _find(self, users: list[dict], uid: str) -> dict:
        for u in users:
            if u["id"] == uid:
                return u
        raise AuthError("usuario nao encontrado", 404)

    @staticmethod
    def public(u: dict) -> dict:
        return {"id": u["id"], "user": u["user"], "role": u["role"], "disabled": bool(u.get("disabled")),
                "totp": bool((u.get("totp") or {}).get("on")), "created": u.get("created"),
                "last_login": u.get("last_login")}

    # ---- auditoria ----------------------------------------------------------------------------------------------
    def audit(self, event: str, user: str = "", ip: str = "", detail: str = "") -> None:
        row = {"t": int(self.now()), "evento": event, "user": user, "ip": ip, "detalhe": detail[:300]}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.dir / "audit.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def read_audit(self, n: int = 200) -> list[dict]:
        try:
            lines = (self.dir / "audit.log").read_text().splitlines()[-n:]
        except OSError:
            return []
        out = []
        for ln in reversed(lines):
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out

    # ---- freio de tentativas ------------------------------------------------------------------------------------
    def locked_for(self, ip: str) -> int:
        st = self.fails.get(ip)
        return 0 if not st or st[1] <= self.now() else math.ceil(st[1] - self.now())

    def _fail(self, ip: str) -> None:
        n = (self.fails.get(ip) or [0, 0])[0] + 1
        lock = 0 if n < 5 else min(900, 30 * 2 ** (n - 5))  # 5 erros seguidos: 30 s, 1 min, 2 min... ate 15 min
        self.fails[ip] = [n, self.now() + lock if lock else 0]
        if len(self.fails) > 2000:
            self.fails = {k: v for k, v in self.fails.items() if v[1] > self.now()}

    def _guard(self, ip: str) -> None:
        wait = self.locked_for(ip)
        if wait:
            raise AuthError(f"muitas tentativas: espere {wait} s", 429)

    # ---- primeiro acesso ----------------------------------------------------------------------------------------
    @property
    def needs_setup(self) -> bool:
        return not self._users()

    def ensure_setup_token(self) -> str | None:
        """Cria (se preciso) o token do primeiro acesso. None quando ja ha usuarios."""
        with self.lock:
            if not self.needs_setup:
                (self.dir / "setup-token").unlink(missing_ok=True)
                return None
            path = self.dir / "setup-token"
            try:
                tok = path.read_text().strip()
                if tok:
                    return tok
            except OSError:
                pass
            self.dir.mkdir(parents=True, exist_ok=True)
            tok = secrets.token_urlsafe(18)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(tok + "\n")
            return tok

    def setup(self, token: str, user: str, password: str, ip: str) -> dict:
        with self.lock:
            self._guard(ip)
            want = self.ensure_setup_token()
            if want is None:
                raise AuthError("o primeiro acesso ja foi feito", 409)
            if not hmac.compare_digest(str(token).strip().encode(), want.encode()):
                self._fail(ip)
                raise AuthError("token de primeiro acesso incorreto", 403)
            u = self._create(check_username(user), password, "admin")
            (self.dir / "setup-token").unlink(missing_ok=True)
            self.audit("primeiro-acesso", u["user"], ip, "admin criado")
            return u

    # ---- usuarios -----------------------------------------------------------------------------------------------
    def _create(self, user: str, password: str, role: str) -> dict:
        if role not in ROLES:
            raise AuthError(f"papel invalido ({' | '.join(ROLES)})")
        check_new_password(password)
        users = self._users()
        if any(u["user"].lower() == user.lower() for u in users):
            raise AuthError("ja existe um usuario com esse nome", 409)
        u = {"id": secrets.token_hex(4), "user": user, "hash": hash_password(password), "role": role,
             "disabled": False, "totp": None, "created": int(self.now()), "last_login": None}
        users.append(u)
        self._save_users(users)
        return u

    def create_user(self, user: str, password: str, role: str) -> dict:
        with self.lock:
            return self.public(self._create(check_username(user), password, role))

    def list_users(self) -> list[dict]:
        return [self.public(u) for u in self._users()]

    def _admins_left(self, users: list[dict], skip: str) -> int:
        return sum(1 for u in users if u["id"] != skip and u["role"] == "admin" and not u.get("disabled"))

    def update_user(self, uid: str, *, role: str | None = None, disabled: bool | None = None,
                    reset_2fa: bool = False) -> dict:
        with self.lock:
            users = self._users()
            u = self._find(users, uid)
            if (role is not None and role != "admin") or disabled:
                if u["role"] == "admin" and not u.get("disabled") and self._admins_left(users, uid) == 0:
                    raise AuthError("precisa restar pelo menos um admin ativo", 409)
            if role is not None:
                if role not in ROLES:
                    raise AuthError(f"papel invalido ({' | '.join(ROLES)})")
                u["role"] = role
            if disabled is not None:
                u["disabled"] = bool(disabled)
            if reset_2fa:
                u["totp"] = None
            self._save_users(users)
            if disabled or role is not None or reset_2fa:
                self._drop_sessions(uid)  # papel/estado novo vale ja: obriga a entrar de novo
            return self.public(u)

    def set_user_password(self, uid: str, password: str) -> None:
        with self.lock:
            check_new_password(password)
            users = self._users()
            u = self._find(users, uid)
            u["hash"] = hash_password(password)
            self._save_users(users)
            self._drop_sessions(uid)

    def delete_user(self, uid: str) -> None:
        with self.lock:
            users = self._users()
            u = self._find(users, uid)
            if u["role"] == "admin" and not u.get("disabled") and self._admins_left(users, uid) == 0:
                raise AuthError("precisa restar pelo menos um admin ativo", 409)
            self._save_users([x for x in users if x["id"] != uid])
            self._drop_sessions(uid)

    def change_password(self, uid: str, current: str, new: str) -> None:
        with self.lock:
            u = self._find(self._users(), uid)
            if not verify_password(current, u["hash"]):
                raise AuthError("senha atual incorreta")
            if verify_password(new, u["hash"]):
                raise AuthError("a nova senha e igual a atual")
            self.set_user_password(uid, new)

    # ---- 2FA ----------------------------------------------------------------------------------------------------
    def _check_totp(self, u: dict, code: str, *, commit: bool = True) -> bool:
        t = u.get("totp") or {}
        if not t.get("secret") or not str(code).strip().isdigit():
            return False
        now_c = int(self.now() // 30)
        for c in (now_c - 1, now_c, now_c + 1):
            if hmac.compare_digest(totp_code(t["secret"], c), str(code).strip()) and c > t.get("last", -1):
                if commit:
                    t["last"] = c  # um codigo so vale uma vez (barra repeticao)
                return True
        return False

    def totp_start(self, uid: str) -> dict:
        with self.lock:
            users = self._users()
            u = self._find(users, uid)
            if (u.get("totp") or {}).get("on"):
                raise AuthError("o 2FA ja esta ativo", 409)
            secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
            u["totp"] = {"secret": secret, "on": False}
            self._save_users(users)
            return {"secret": secret, "uri": totp_uri(u["user"], secret)}

    def totp_enable(self, uid: str, code: str) -> None:
        with self.lock:
            users = self._users()
            u = self._find(users, uid)
            if not u.get("totp") or u["totp"].get("on"):
                raise AuthError("comece pela chave do 2FA", 409)
            if not self._check_totp(u, code):
                raise AuthError("codigo incorreto")
            u["totp"]["on"] = True
            self._save_users(users)

    def totp_disable(self, uid: str, password: str) -> None:
        with self.lock:
            users = self._users()
            u = self._find(users, uid)
            if not verify_password(password, u["hash"]):
                raise AuthError("senha incorreta")
            u["totp"] = None
            self._save_users(users)

    # ---- sessoes ------------------------------------------------------------------------------------------------
    @staticmethod
    def _sid(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def login(self, user: str, password: str, ip: str, *, code: str = "", remember: bool = False,
              agent: str = "") -> tuple[str, int, dict]:
        """Devolve (cookie, ttl_s, usuario) ou levanta AuthError. Mesma mensagem para usuario e senha errados."""
        with self.lock:
            self._guard(ip)
            users = self._users()
            if not users:
                raise AuthError("nenhum usuario ainda: faca o primeiro acesso", 503)
            u = next((x for x in users if x["user"].lower() == str(user).strip().lower()), None)
            ok = verify_password(password, u["hash"] if u else hash_password("x", iterations=1000))
            if not (u and ok) or u.get("disabled"):
                self._fail(ip)
                self.audit("login-falhou", str(user)[:40], ip)
                raise AuthError("usuario ou senha incorretos", 401)
            if (u.get("totp") or {}).get("on"):
                if not str(code).strip():
                    raise AuthError("digite o codigo do aplicativo autenticador", 401, need_code=True)
                if not self._check_totp(u, code):
                    self._fail(ip)
                    self.audit("2fa-falhou", u["user"], ip)
                    raise AuthError("codigo incorreto ou expirado", 401, need_code=True)
            self.fails.pop(ip, None)
            u["last_login"] = int(self.now())
            self._save_users(users)  # tambem grava o ultimo codigo 2FA usado
            token = secrets.token_urlsafe(32)
            ttl = REMEMBER_TTL_S if remember else SESSION_TTL_S
            sessions = {k: v for k, v in self._sessions().items() if v["exp"] > self.now()}
            sessions[self._sid(token)] = {"uid": u["id"], "exp": int(self.now()) + ttl, "created": int(self.now()),
                                          "ip": ip, "agent": agent[:120]}
            self._write("sessions.json", sessions)
            self.audit("login", u["user"], ip, "lembrar" if remember else "")
            return token, ttl, self.public(u)

    def session(self, cookie_header: str | None) -> dict | None:
        """Sessao valida -> {sid, id, user, role, totp}; senao None. Usuario removido/desativado = sem sessao."""
        if not cookie_header:
            return None
        try:
            morsel = SimpleCookie(cookie_header).get(COOKIE)
        except Exception:  # noqa: BLE001 - cabecalho Cookie malformado
            return None
        if morsel is None or not morsel.value:
            return None
        sid = self._sid(morsel.value)
        with self.lock:
            s = self._sessions().get(sid)
            if not s or s["exp"] <= self.now():
                return None
            u = next((x for x in self._users() if x["id"] == s["uid"]), None)
            if u is None or u.get("disabled"):
                return None
        self.mem[sid] = self.now()
        return {"sid": sid[:12], **self.public(u)}

    def _drop_sessions(self, uid: str, keep: str | None = None) -> int:
        sessions = self._sessions()
        keep_full = [k for k in sessions if keep and k.startswith(keep)]
        kept = {k: v for k, v in sessions.items() if v["uid"] != uid or k in keep_full}
        self._write("sessions.json", kept)
        return len(sessions) - len(kept)

    def logout(self, cookie_header: str | None) -> None:
        if not cookie_header:
            return
        try:
            morsel = SimpleCookie(cookie_header).get(COOKIE)
        except Exception:  # noqa: BLE001
            return
        if morsel is None:
            return
        with self.lock:
            s = self._sessions()
            if s.pop(self._sid(morsel.value), None) is not None:
                self._write("sessions.json", s)

    def list_sessions(self, uid: str, current: str = "") -> list[dict]:
        out = []
        for k, v in self._sessions().items():
            if v["uid"] == uid and v["exp"] > self.now():
                out.append({"id": k[:12], "criada": v["created"], "expira": v["exp"], "ip": v.get("ip", ""),
                            "agent": v.get("agent", ""), "ultimo_uso": int(self.mem.get(k, v["created"])),
                            "atual": k[:12] == current})
        return sorted(out, key=lambda x: -x["criada"])

    def revoke_session(self, uid: str, sid: str, *, admin: bool = False) -> bool:
        with self.lock:
            s = self._sessions()
            hit = [k for k, v in s.items() if k.startswith(sid) and len(sid) >= 8 and (admin or v["uid"] == uid)]
            for k in hit:
                s.pop(k)
            if hit:
                self._write("sessions.json", s)
            return bool(hit)

    def revoke_others(self, uid: str, current: str) -> int:
        with self.lock:
            return self._drop_sessions(uid, keep=current)


def cookie_header(value: str, ttl: int, *, path: str = "/", secure: bool = True) -> str:
    parts = [f"{COOKIE}={value}", f"Max-Age={ttl}", f"Path={path}", "HttpOnly", "SameSite=Strict"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    auth = Auth.from_env()
    if len(args) >= 1 and args[0] == "set-password":
        user = args[1] if len(args) > 1 else "admin"
        pw, again = getpass.getpass(f"nova senha de '{user}': "), getpass.getpass("repita a senha: ")
        if pw != again:
            print("as senhas nao conferem", file=sys.stderr)
            return 1
        try:
            with auth.lock:
                found = next((u for u in auth._users() if u["user"].lower() == user.lower()), None)
                if found:
                    auth.set_user_password(found["id"], pw)
                    auth.update_user(found["id"], disabled=False)
                else:
                    auth._create(check_username(user), pw, "admin")
        except AuthError as e:
            print(f"recusada: {e}", file=sys.stderr)
            return 1
        auth.audit("senha-definida-na-vm", user, "vm")
        print(f"senha de '{user}' gravada ({'conta existente' if found else 'novo admin'}); sessoes dele encerradas")
        return 0
    if len(args) == 2 and args[0] == "reset-2fa":
        found = next((u for u in auth._users() if u["user"].lower() == args[1].lower()), None)
        if not found:
            print("usuario nao encontrado", file=sys.stderr)
            return 1
        auth.update_user(found["id"], reset_2fa=True)
        auth.audit("2fa-removido-na-vm", args[1], "vm")
        print("2FA removido")
        return 0
    print("uso: python -m quant.auth set-password [usuario] | reset-2fa usuario", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
