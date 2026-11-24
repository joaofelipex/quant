"""Login do painel: hash de senha, sessao em cookie, freio de tentativas e as rotas protegidas de quant.control."""
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from quant import auth as authmod
from quant import control
from quant.auth import Auth, AuthError

SENHA = "uma-senha-de-teste-123"
NOVA = "nova-senha-forte-1"
ERRADA = "errada-errada-1"


@pytest.fixture(autouse=True)
def rapido(monkeypatch):
    monkeypatch.setattr(authmod, "ITERATIONS", 1000)  # PBKDF2 de producao e lento de proposito


@pytest.fixture
def clock():
    return {"t": 1_000_000.0}


@pytest.fixture
def auth(tmp_path, clock):
    a = Auth(tmp_path / "auth.json", tmp_path / "key", now=lambda: clock["t"])
    a.set_password("painel", SENHA)
    return a


def cookie(v):
    return f"{authmod.COOKIE}={v}"


class TestSenha:
    def test_hash_nao_guarda_texto_e_verifica(self):
        h = authmod.hash_password(SENHA)
        assert SENHA not in h and h.startswith("pbkdf2_sha256$")
        assert authmod.verify_password(SENHA, h) and not authmod.verify_password(SENHA + "x", h)
        assert authmod.hash_password(SENHA) != h  # sal aleatorio

    @pytest.mark.parametrize("lixo", ["", "x", "a$b$c$d", "pbkdf2_sha256$x$y$z"])
    def test_hash_corrompido_nao_valida(self, lixo):
        assert not authmod.verify_password(SENHA, lixo)

    @pytest.mark.parametrize("fraca", ["curta", "aaaaaaaaaaaa", "1234567890"])
    def test_recusa_senha_fraca(self, tmp_path, fraca):
        with pytest.raises(AuthError):
            Auth(tmp_path / "a", tmp_path / "k").set_password("painel", fraca)

    def test_arquivo_sem_texto_da_senha(self, auth):
        assert SENHA not in auth.auth_file.read_text()


class TestSessao:
    def test_login_ok_gera_cookie_valido(self, auth):
        v, ttl = auth.login("painel", SENHA, "1.1.1.1")
        assert ttl == authmod.SESSION_TTL_S and auth.user_from_cookie(cookie(v)) == "painel"

    def test_lembrar_dura_mais(self, auth):
        assert auth.login("painel", SENHA, "1.1.1.1", remember=True)[1] == authmod.REMEMBER_TTL_S

    @pytest.mark.parametrize("u,p", [("painel", ERRADA), ("outro", SENHA), ("", "")])
    def test_erro_tem_mensagem_unica(self, auth, u, p):
        with pytest.raises(AuthError) as e:
            auth.login(u, p, "1.1.1.1")
        assert str(e.value) == "usuario ou senha incorretos" and e.value.status == 401

    def test_cookie_expira(self, auth, clock):
        v, ttl = auth.login("painel", SENHA, "1.1.1.1")
        clock["t"] += ttl + 1
        assert auth.user_from_cookie(cookie(v)) is None

    def test_cookie_adulterado_ou_de_outro_segredo(self, auth, tmp_path):
        v, _ = auth.login("painel", SENHA, "1.1.1.1")
        body, sig = v.rsplit(".", 1)
        assert auth.user_from_cookie(cookie(body + "." + "A" * len(sig))) is None
        assert auth.user_from_cookie(cookie("lixo")) is None and auth.user_from_cookie(None) is None
        assert Auth(auth.auth_file, tmp_path / "outra-chave").user_from_cookie(cookie(v)) is None

    def test_trocar_a_senha_derruba_as_sessoes(self, auth):
        v, _ = auth.login("painel", SENHA, "1.1.1.1")
        auth.change_password("painel", SENHA, NOVA)
        assert auth.user_from_cookie(cookie(v)) is None
        assert auth.login("painel", NOVA, "1.1.1.1")

    def test_troca_exige_senha_atual(self, auth):
        with pytest.raises(AuthError, match="atual incorreta"):
            auth.change_password("painel", ERRADA, NOVA)
        with pytest.raises(AuthError, match="igual"):
            auth.change_password("painel", SENHA, SENHA)

    def test_sem_senha_definida(self, tmp_path):
        a = Auth(tmp_path / "nada", tmp_path / "k")
        assert not a.configured
        with pytest.raises(AuthError) as e:
            a.login("painel", SENHA, "1.1.1.1")
        assert e.value.status == 503


class TestFreio:
    def test_bloqueia_apos_5_erros_e_libera_com_o_tempo(self, auth, clock):
        for _ in range(5):
            with pytest.raises(AuthError):
                auth.login("painel", ERRADA, "9.9.9.9")
        with pytest.raises(AuthError) as e:  # ate a senha certa e recusada durante o bloqueio
            auth.login("painel", SENHA, "9.9.9.9")
        assert e.value.status == 429 and "espere" in str(e.value)
        assert auth.login("painel", SENHA, "8.8.8.8")  # outro IP nao e afetado
        clock["t"] += 31
        assert auth.login("painel", SENHA, "9.9.9.9")

    def test_bloqueio_cresce(self, auth, clock):
        for _ in range(5):
            with pytest.raises(AuthError):
                auth.login("painel", ERRADA, "7.7.7.7")
        first = auth.locked_for("7.7.7.7")
        clock["t"] += first + 1
        with pytest.raises(AuthError):
            auth.login("painel", ERRADA, "7.7.7.7")
        assert auth.locked_for("7.7.7.7") > first


@pytest.fixture
def server(tmp_path, auth, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html>app</html>")
    monkeypatch.setenv("QUANT_WEB_DIR", str(tmp_path / "web"))
    handler = control.make_handler(tmp_path / "st.json", tmp_path / "KILL", tmp_path / "rt.env", auth=auth)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(url, method="GET", body=None, cook=None, headers=None):
    h = {"X-Quant-Control": "1", "Content-Type": "application/json", **(headers or {})}
    if cook:
        h["Cookie"] = cook
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


def entrar(server, **kw):
    code, body, hdr = call(server + "/api/login", "POST", {"user": "painel", "password": SENHA, **kw},
                           headers={"X-Forwarded-Proto": "https"})
    assert code == 200, body
    return hdr["Set-Cookie"].split(";")[0], hdr["Set-Cookie"]


class TestHttp:
    @pytest.mark.parametrize("path", ["/api/status", "/api/trades", "/api/settings", "/api/order", "/api/session",
                                      "/api/trades.csv"])
    def test_rotas_exigem_login(self, server, path):
        code, body, _ = call(server + path)
        assert code == 401 and body["configurado"] is True

    @pytest.mark.parametrize("path", ["/api/kill", "/api/runner/stop", "/api/order", "/api/settings",
                                      "/api/deploy/run", "/api/password"])
    def test_acoes_exigem_login(self, server, path):
        assert call(server + path, "POST", {})[0] == 401

    def test_pagina_do_app_e_publica_para_mostrar_o_login(self, server):
        with urllib.request.urlopen(server + "/", timeout=10) as r:
            assert r.status == 200 and b"app" in r.read()

    def test_login_define_cookie_seguro(self, server):
        _, raw = entrar(server)
        for flag in ("HttpOnly", "SameSite=Strict", "Secure", "Max-Age=43200", "Path=/"):
            assert flag in raw
        assert raw.split(";")[0].startswith("quant_session=")

    def test_sem_https_nao_marca_secure(self, server):
        code, _, hdr = call(server + "/api/login", "POST", {"user": "painel", "password": SENHA})
        assert code == 200 and "Secure" not in hdr["Set-Cookie"]

    def test_sessao_libera_rotas_e_logout_limpa(self, server):
        cook, _ = entrar(server)
        assert call(server + "/api/session", cook=cook)[1]["user"] == "painel"
        assert call(server + "/api/settings", cook=cook)[0] == 200
        code, _, hdr = call(server + "/api/logout", "POST", {})
        assert code == 200 and "Max-Age=0" in hdr["Set-Cookie"]

    def test_login_errado(self, server):
        code, body, hdr = call(server + "/api/login", "POST", {"user": "painel", "password": ERRADA})
        assert code == 401 and "incorretos" in body["erro"] and "Set-Cookie" not in hdr

    def test_login_sem_cabecalho_csrf_e_barrado(self, server):
        req = urllib.request.Request(server + "/api/login", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 403

    def test_ip_vem_do_nginx_quando_o_par_e_local(self, server, auth):
        for _ in range(5):
            call(server + "/api/login", "POST", {"user": "painel", "password": ERRADA},
                 headers={"X-Real-IP": "5.5.5.5"})
        assert auth.locked_for("5.5.5.5") > 0 and auth.locked_for("127.0.0.1") == 0
        code = call(server + "/api/login", "POST", {"user": "painel", "password": SENHA},
                    headers={"X-Real-IP": "5.5.5.5"})[0]
        assert code == 429

    def test_trocar_senha_pelo_painel(self, server, auth):
        cook, _ = entrar(server)
        code, body, _ = call(server + "/api/password", "POST", {"atual": ERRADA, "nova": NOVA}, cook)
        assert code == 400 and "incorreta" in body["erro"]
        code, _, hdr = call(server + "/api/password", "POST", {"atual": SENHA, "nova": NOVA}, cook)
        assert code == 200 and "Max-Age=0" in hdr["Set-Cookie"]
        assert call(server + "/api/session", cook=cook)[0] == 401  # sessao antiga morreu
        assert auth.login("painel", NOVA, "3.3.3.3")


def test_cli_define_senha(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_AUTH_FILE", str(tmp_path / "a.json"))
    monkeypatch.setenv("QUANT_SESSION_KEY", str(tmp_path / "k"))
    senhas = iter(["cli-senha-forte-77", "cli-senha-forte-77"])
    monkeypatch.setattr("getpass.getpass", lambda *_: next(senhas))
    assert authmod.main(["set-password", "admin"]) == 0
    assert Auth.from_env(os.environ.get).login("admin", "cli-senha-forte-77", "1.1.1.1")
    senhas = iter(["cli-senha-forte-77", "diferente-diferente"])
    assert authmod.main(["set-password"]) == 1
