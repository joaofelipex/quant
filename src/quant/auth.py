"""Login do painel: senha com PBKDF2, sessao em cookie assinado e freio de tentativas. So stdlib.

    sudo -u quant /opt/quant/.venv/bin/python -m quant.auth set-password     # define/troca a senha (pergunta)

A senha NUNCA fica em texto: so o hash (``pbkdf2_sha256$iteracoes$sal$hash``) vai para ``QUANT_AUTH_FILE``. O cookie e
``usuario.expira.versao`` assinado com HMAC-SHA256 por um segredo proprio (``QUANT_SESSION_KEY``, criado na
primeira vez, modo 0600); trocar a senha muda a ``versao`` e derruba todas as sessoes abertas.
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
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path

ITERATIONS = 600_000
MIN_PASSWORD = 10
COOKIE = "quant_session"
SESSION_TTL_S = 12 * 3600
REMEMBER_TTL_S = 7 * 24 * 3600
DEFAULT_USER = "painel"
AUTH_FILE = Path("/var/lib/quant/auth.json")
KEY_FILE = Path("/var/lib/quant/session.key")


class AuthError(ValueError):
    """Pedido de login/senha recusado (mensagem em portugues, vai para a tela). ``status`` = codigo HTTP."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


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
    if pw.lower() in {"password123", "1234567890", "qwertyuiop"} or len(set(pw)) < 4:
        raise AuthError("senha fraca demais: misture letras, numeros e simbolos")


class Auth:
    def __init__(self, auth_file: Path = AUTH_FILE, key_file: Path = KEY_FILE, *, now=time.time):
        self.auth_file, self.key_file, self.now = Path(auth_file), Path(key_file), now
        self.fails: dict[str, list[float]] = {}  # ip -> [falhas seguidas, bloqueado_ate]

    @classmethod
    def from_env(cls, env=os.environ.get) -> Auth:
        return cls(Path(env("QUANT_AUTH_FILE", str(AUTH_FILE))), Path(env("QUANT_SESSION_KEY", str(KEY_FILE))))

    # ---- credenciais ----------------------------------------------------------------------------------------------
    def _load(self) -> dict | None:
        try:
            d = json.loads(self.auth_file.read_text())
            return d if isinstance(d, dict) and d.get("user") and d.get("hash") else None
        except (OSError, ValueError):
            return None

    @property
    def configured(self) -> bool:
        return self._load() is not None

    def set_password(self, user: str, password: str) -> None:
        check_new_password(password)
        if not user or len(user) > 40 or not user.replace("-", "").replace("_", "").isalnum():
            raise AuthError("usuario invalido (letras, numeros, - e _)")
        self.auth_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.auth_file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"user": user, "hash": hash_password(password), "changed": int(self.now())}, f)
        tmp.replace(self.auth_file)

    def _secret(self) -> bytes:
        try:
            k = self.key_file.read_bytes()
            if len(k) >= 32:
                return k
        except OSError:
            pass
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        k = secrets.token_bytes(48)
        fd = os.open(self.key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
        return k

    # ---- freio de tentativas --------------------------------------------------------------------------------------
    def locked_for(self, ip: str) -> int:
        st = self.fails.get(ip)
        return 0 if not st or st[1] <= self.now() else math.ceil(st[1] - self.now())

    def _fail(self, ip: str) -> None:
        n = (self.fails.get(ip) or [0, 0])[0] + 1
        lock = 0 if n < 5 else min(900, 30 * 2 ** (n - 5))  # 5 erros seguidos: 30 s, 60 s, 2 min... ate 15 min
        self.fails[ip] = [n, self.now() + lock if lock else 0]
        if len(self.fails) > 2000:
            self.fails = {k: v for k, v in self.fails.items() if v[1] > self.now()}

    # ---- login / sessao -------------------------------------------------------------------------------------------
    def login(self, user: str, password: str, ip: str, remember: bool = False) -> tuple[str, int]:
        """Devolve (cookie, ttl_s) ou levanta AuthError. A mesma mensagem para usuario e senha errados."""
        wait = self.locked_for(ip)
        if wait:
            raise AuthError(f"muitas tentativas: espere {wait} s", 429)
        cred = self._load()
        if cred is None:
            raise AuthError("senha ainda nao definida: veja deploy/README.md (definir-senha.sh)", 503)
        ok_pw = verify_password(password, cred["hash"])
        ok_user = hmac.compare_digest(str(user).encode(), cred["user"].encode())
        if not (ok_pw and ok_user):
            self._fail(ip)
            raise AuthError("usuario ou senha incorretos", 401)
        self.fails.pop(ip, None)
        ttl = REMEMBER_TTL_S if remember else SESSION_TTL_S
        return self._token(cred, ttl), ttl

    def _token(self, cred: dict, ttl: int) -> str:
        payload = f"{cred['user']}.{int(self.now()) + ttl}.{cred['hash'][-8:]}"
        body = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        return f"{body}.{self._sign(body)}"

    def _sign(self, body: str) -> str:
        mac = hmac.new(self._secret(), body.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def user_from_cookie(self, header: str | None) -> str | None:
        """Usuario da sessao valida (assinatura, validade e versao da senha), ou None."""
        if not header:
            return None
        try:
            morsel = SimpleCookie(header).get(COOKIE)
            if morsel is None:
                return None
            body, sig = morsel.value.rsplit(".", 1)
            if not hmac.compare_digest(sig, self._sign(body)):
                return None
            user, exp, ver = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split(".")
            cred = self._load()
            if cred is None or user != cred["user"] or ver != cred["hash"][-8:] or int(exp) < self.now():
                return None
            return user
        except (ValueError, KeyError, UnicodeDecodeError):
            return None

    def change_password(self, user: str, current: str, new: str) -> None:
        cred = self._load()
        if cred is None or not verify_password(current, cred["hash"]):
            raise AuthError("senha atual incorreta")
        if verify_password(new, cred["hash"]):
            raise AuthError("a nova senha e igual a atual")
        self.set_password(user, new)


def cookie_header(value: str, ttl: int, *, path: str = "/", secure: bool = True) -> str:
    parts = [f"{COOKIE}={value}", f"Max-Age={ttl}", f"Path={path}", "HttpOnly", "SameSite=Strict"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] != "set-password":
        print("uso: python -m quant.auth set-password [usuario]", file=sys.stderr)
        return 2
    user = args[1] if len(args) > 1 else DEFAULT_USER
    auth = Auth.from_env()
    pw, again = getpass.getpass(f"nova senha de '{user}': "), getpass.getpass("repita a senha: ")
    if pw != again:
        print("as senhas nao conferem", file=sys.stderr)
        return 1
    try:
        auth.set_password(user, pw)
    except AuthError as e:
        print(f"recusada: {e}", file=sys.stderr)
        return 1
    print(f"senha de '{user}' gravada em {auth.auth_file}; todas as sessoes abertas foram encerradas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
