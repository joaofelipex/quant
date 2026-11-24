"""Contas do painel: senha, primeiro acesso, papeis, sessoes no servidor, 2FA, auditoria e as rotas protegidas."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from quant import accounts, control
from quant import auth as authmod
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
    a = Auth(tmp_path / "d", now=lambda: clock["t"])
    a.setup("chefe", SENHA, "1.1.1.1")
    return a


def cookie(v):
    return f"{authmod.COOKIE}={v}"


def entrar(a, user="chefe", pw=SENHA, ip="1.1.1.1", **kw):
    token, ttl, u = a.login(user, pw, ip, **kw)
    return token, ttl, u


class TestSenha:
    def test_hash_nao_guarda_texto_e_verifica(self):
        h = authmod.hash_password(SENHA)
        assert SENHA not in h and h.startswith("pbkdf2_sha256$")
        assert authmod.verify_password(SENHA, h) and not authmod.verify_password(SENHA + "x", h)
        assert authmod.hash_password(SENHA) != h

    @pytest.mark.parametrize("lixo", ["", "x", "a$b$c$d", "pbkdf2_sha256$x$y$z"])
    def test_hash_corrompido_nao_valida(self, lixo):
        assert not authmod.verify_password(SENHA, lixo)

    @pytest.mark.parametrize("fraca", ["curta", "aaaaaaaaaaaa", "1234567890"])
    def test_recusa_senha_fraca(self, fraca):
        with pytest.raises(AuthError):
            authmod.check_new_password(fraca)

    @pytest.mark.parametrize("nome", ["", " ", "a b", "x" * 41, "ro/ot", "a;b"])
    def test_recusa_usuario_invalido(self, nome):
        with pytest.raises(AuthError):
            authmod.check_username(nome)


class TestPrimeiroAcesso:
    def test_sem_usuarios_precisa_de_setup(self, tmp_path):
        assert Auth(tmp_path / "d").needs_setup

    def test_setup_cria_admin_e_fecha_a_rota(self, tmp_path):
        a = Auth(tmp_path / "d")
        a.setup("chefe", SENHA, "1.1.1.1")
        assert not a.needs_setup and a.list_users()[0]["role"] == "admin"
        with pytest.raises(AuthError) as e:  # o segundo visitante nao vira admin
            a.setup("intruso", SENHA, "1.1.1.1")
        assert e.value.status == 409 and len(a.list_users()) == 1

    def test_setup_valida_usuario_e_senha(self, tmp_path):
        a = Auth(tmp_path / "d")
        for u, p in (("a b", SENHA), ("chefe", "curta")):
            with pytest.raises(AuthError):
                a.setup(u, p, "1.1.1.1")
        assert a.needs_setup

    def test_setup_tem_freio_por_ip(self, tmp_path):
        a = Auth(tmp_path / "d")
        for _ in range(5):
            a._fail("9.9.9.9")
        with pytest.raises(AuthError) as e:
            a.setup("chefe", SENHA, "9.9.9.9")
        assert e.value.status == 429 and a.needs_setup

    def test_login_sem_usuarios(self, tmp_path):
        with pytest.raises(AuthError) as e:
            Auth(tmp_path / "d").login("x", "y", "1.1.1.1")
        assert e.value.status == 503


class TestSessao:
    def test_login_ok_e_cookie_opaco(self, auth, tmp_path):
        token, ttl, _ = entrar(auth)
        s = auth.session(cookie(token))
        assert ttl == authmod.SESSION_TTL_S and s["user"] == "chefe" and s["role"] == "admin"
        assert token not in (tmp_path / "d" / "sessions.json").read_text()  # so o hash fica no disco

    def test_lembrar_dura_mais(self, auth):
        assert entrar(auth, remember=True)[1] == authmod.REMEMBER_TTL_S

    @pytest.mark.parametrize("u,p", [("chefe", ERRADA), ("outro", SENHA), ("", "")])
    def test_erro_tem_mensagem_unica(self, auth, u, p):
        with pytest.raises(AuthError) as e:
            auth.login(u, p, "1.1.1.1")
        assert str(e.value) == "usuario ou senha incorretos" and e.value.status == 401

    def test_usuario_nao_diferencia_maiusculas(self, auth):
        assert auth.login("CHEFE", SENHA, "1.1.1.1")

    def test_cookie_expira(self, auth, clock):
        token, ttl, _ = entrar(auth)
        clock["t"] += ttl + 1
        assert auth.session(cookie(token)) is None

    def test_cookie_falso_ou_malformado(self, auth):
        for h in (None, "", "lixo", cookie("inventado"), cookie(""), "quant_session=a=b;;;"):
            assert auth.session(h) is None

    def test_logout_invalida(self, auth):
        token, _, _ = entrar(auth)
        auth.logout(cookie(token))
        assert auth.session(cookie(token)) is None

    def test_sessoes_sobrevivem_a_reinicio(self, auth, tmp_path, clock):
        token, _, _ = entrar(auth)
        outra = Auth(tmp_path / "d", now=lambda: clock["t"])  # processo novo, mesmo disco
        assert outra.session(cookie(token))["user"] == "chefe"

    def test_trocar_a_senha_derruba_as_sessoes(self, auth):
        token, _, u = entrar(auth)
        auth.change_password(u["id"], SENHA, NOVA)
        assert auth.session(cookie(token)) is None
        assert auth.login("chefe", NOVA, "1.1.1.1")

    def test_troca_exige_senha_atual(self, auth):
        uid = auth.list_users()[0]["id"]
        with pytest.raises(AuthError, match="atual incorreta"):
            auth.change_password(uid, ERRADA, NOVA)
        with pytest.raises(AuthError, match="igual"):
            auth.change_password(uid, SENHA, SENHA)

    def test_listar_e_encerrar_sessoes(self, auth):
        t1, _, u = entrar(auth, agent="Firefox")
        t2, _, _ = entrar(auth, agent="Chrome")
        cur = auth.session(cookie(t1))["sid"]
        lista = auth.list_sessions(u["id"], cur)
        assert len(lista) == 2 and sum(s["atual"] for s in lista) == 1
        other = next(s["id"] for s in lista if not s["atual"])
        assert auth.revoke_session(u["id"], other)
        assert auth.session(cookie(t2)) is None and auth.session(cookie(t1))
        assert auth.revoke_others(u["id"], cur) == 0

    def test_nao_encerra_sessao_de_outro_usuario(self, auth):
        outro = auth.create_user("ana", SENHA, "leitor")
        t, _, _ = entrar(auth, "ana")
        sid = auth.session(cookie(t))["sid"]
        chefe = next(u["id"] for u in auth.list_users() if u["user"] == "chefe")
        assert not auth.revoke_session(chefe, sid)  # nao e dele
        assert auth.revoke_session(chefe, sid, admin=True) and outro


class TestFreio:
    def test_bloqueia_apos_5_erros_e_libera_com_o_tempo(self, auth, clock):
        for _ in range(5):
            with pytest.raises(AuthError):
                auth.login("chefe", ERRADA, "9.9.9.9")
        with pytest.raises(AuthError) as e:
            auth.login("chefe", SENHA, "9.9.9.9")
        assert e.value.status == 429
        assert auth.login("chefe", SENHA, "8.8.8.8")
        clock["t"] += 31
        assert auth.login("chefe", SENHA, "9.9.9.9")

    def test_bloqueio_cresce(self, auth, clock):
        for _ in range(5):
            with pytest.raises(AuthError):
                auth.login("chefe", ERRADA, "7.7.7.7")
        first = auth.locked_for("7.7.7.7")
        clock["t"] += first + 1
        with pytest.raises(AuthError):
            auth.login("chefe", ERRADA, "7.7.7.7")
        assert auth.locked_for("7.7.7.7") > first


class TestUsuarios:
    def test_criar_listar_sem_hash(self, auth):
        u = auth.create_user("ana", SENHA, "operador")
        assert u["role"] == "operador" and "hash" not in u
        assert {x["user"] for x in auth.list_users()} == {"chefe", "ana"}
        with pytest.raises(AuthError, match="ja existe"):
            auth.create_user("ANA", SENHA, "leitor")
        with pytest.raises(AuthError, match="papel"):
            auth.create_user("bia", SENHA, "dono")

    def test_desativar_derruba_sessao_e_bloqueia_login(self, auth):
        u = auth.create_user("ana", SENHA, "leitor")
        t, _, _ = entrar(auth, "ana")
        auth.update_user(u["id"], disabled=True)
        assert auth.session(cookie(t)) is None
        with pytest.raises(AuthError):
            auth.login("ana", SENHA, "1.1.1.1")
        auth.update_user(u["id"], disabled=False)
        assert auth.login("ana", SENHA, "1.1.1.1")

    def test_mudar_papel_derruba_sessoes(self, auth):
        u = auth.create_user("ana", SENHA, "leitor")
        t, _, _ = entrar(auth, "ana")
        auth.update_user(u["id"], role="operador")
        assert auth.session(cookie(t)) is None
        assert auth.login("ana", SENHA, "1.1.1.1")[2]["role"] == "operador"

    def test_nunca_fica_sem_admin(self, auth):
        chefe = auth.list_users()[0]["id"]
        for kw in ({"role": "leitor"}, {"disabled": True}):
            with pytest.raises(AuthError, match="admin ativo"):
                auth.update_user(chefe, **kw)
        with pytest.raises(AuthError, match="admin ativo"):
            auth.delete_user(chefe)
        auth.create_user("outro", SENHA, "admin")
        auth.update_user(chefe, role="operador")  # agora ha outro admin

    def test_admin_redefine_senha_e_apaga(self, auth):
        u = auth.create_user("ana", SENHA, "leitor")
        t, _, _ = entrar(auth, "ana")
        auth.set_user_password(u["id"], NOVA)
        assert auth.session(cookie(t)) is None and auth.login("ana", NOVA, "1.1.1.1")
        auth.delete_user(u["id"])
        assert len(auth.list_users()) == 1
        with pytest.raises(AuthError, match="nao encontrado"):
            auth.delete_user(u["id"])


class TestDoisFatores:
    def ativar(self, auth, clock):
        uid = auth.list_users()[0]["id"]
        sec = auth.totp_start(uid)["secret"]
        auth.totp_enable(uid, authmod.totp_code(sec, int(clock["t"] // 30)))
        return uid, sec

    def test_vetor_rfc6238(self):
        # RFC 6238, SHA-1, segredo ASCII "12345678901234567890", t=59 s: 94287082 com 8 digitos, entao 287082 com 6
        sec = authmod.base64.b32encode(b"12345678901234567890").decode()
        assert authmod.totp_code(sec, 59 // 30) == "287082"

    def test_ativar_e_exigir_codigo_no_login(self, auth, clock):
        uid, sec = self.ativar(auth, clock)
        assert next(u for u in auth.list_users() if u["id"] == uid)["totp"] is True
        with pytest.raises(AuthError) as e:
            auth.login("chefe", SENHA, "1.1.1.1")
        assert e.value.need_code and e.value.status == 401
        clock["t"] += 60  # o codigo do enable ja foi usado e o proximo e outro
        assert auth.login("chefe", SENHA, "1.1.1.1", code=authmod.totp_code(sec, int(clock["t"] // 30)))

    def test_codigo_errado_conta_como_falha(self, auth, clock):
        self.ativar(auth, clock)
        with pytest.raises(AuthError, match="incorreto"):
            auth.login("chefe", SENHA, "1.1.1.1", code="000000")

    def test_codigo_nao_vale_duas_vezes(self, auth, clock):
        _, sec = self.ativar(auth, clock)
        clock["t"] += 30
        code = authmod.totp_code(sec, int(clock["t"] // 30))
        assert auth.login("chefe", SENHA, "1.1.1.1", code=code)
        with pytest.raises(AuthError):
            auth.login("chefe", SENHA, "1.1.1.1", code=code)

    def test_enable_com_codigo_errado_e_desativar_exige_senha(self, auth, clock):
        uid = auth.list_users()[0]["id"]
        auth.totp_start(uid)
        with pytest.raises(AuthError, match="incorreto"):
            auth.totp_enable(uid, "123456")
        _, _ = self.ativar(auth, clock)
        with pytest.raises(AuthError, match="senha incorreta"):
            auth.totp_disable(uid, ERRADA)
        auth.totp_disable(uid, SENHA)
        assert auth.login("chefe", SENHA, "1.1.1.1")

    def test_admin_remove_2fa_de_outro(self, auth, clock):
        uid, _ = self.ativar(auth, clock)
        auth.update_user(uid, reset_2fa=True)
        assert auth.login("chefe", SENHA, "1.1.1.1")


class TestAuditoria:
    def test_registra_login_e_falha_do_mais_novo_ao_mais_velho(self, auth):
        with pytest.raises(AuthError):
            auth.login("chefe", ERRADA, "5.5.5.5")
        auth.login("chefe", SENHA, "5.5.5.5")
        ev = [e["evento"] for e in auth.read_audit()]
        assert ev[:2] == ["login", "login-falhou"] and "primeiro-acesso" in ev

    def test_log_nao_guarda_senha(self, auth, tmp_path):
        with pytest.raises(AuthError):
            auth.login("chefe", ERRADA, "5.5.5.5")
        assert ERRADA not in (tmp_path / "d" / "audit.log").read_text()


class TestPapeis:
    @pytest.mark.parametrize("m,p,need", [
        ("GET", "/api/session", None), ("POST", "/api/login", None), ("POST", "/api/setup", None),
        ("GET", "/api/status", "leitor"), ("GET", "/api/trades.csv", "leitor"), ("GET", "/api/order", "leitor"),
        ("GET", "/api/sessions", "any"), ("GET", "/api/users", "admin"), ("GET", "/api/audit", "admin"),
        ("POST", "/api/password", "any"), ("POST", "/api/2fa/start", "any"),
        ("POST", "/api/order", "operador"), ("POST", "/api/runner/stop", "operador"), ("POST", "/api/kill", "operador"),
        ("POST", "/api/settings", "operador"), ("POST", "/api/alerts/test", "operador"),
        ("POST", "/api/deploy/run", "admin"), ("POST", "/api/deploy/rollback", "admin"),
        ("POST", "/api/users", "admin"),
        ("POST", "/api/users/x/delete", "admin"), ("POST", "/api/rota-nova", "admin"),
    ])
    def test_tabela(self, m, p, need):
        assert accounts.required_role(m, p) == need

    def test_hierarquia(self):
        assert accounts.allowed("admin", "operador") and accounts.allowed("operador", "leitor")
        assert not accounts.allowed("leitor", "operador") and not accounts.allowed("operador", "admin")
        assert accounts.allowed("leitor", "any")


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


def web_login(server, user="chefe", pw=SENHA, **kw):
    code, body, hdr = call(server + "/api/login", "POST", {"user": user, "password": pw, **kw},
                           headers={"X-Forwarded-Proto": "https"})
    assert code == 200, body
    return hdr["Set-Cookie"].split(";")[0], hdr["Set-Cookie"]


class TestHttp:
    @pytest.mark.parametrize("path", ["/api/status", "/api/trades", "/api/settings", "/api/order", "/api/sessions",
                                      "/api/trades.csv", "/api/users", "/api/audit"])
    def test_leituras_exigem_login(self, server, path):
        assert call(server + path)[0] == 401

    @pytest.mark.parametrize("path", ["/api/kill", "/api/runner/stop", "/api/order", "/api/settings",
                                      "/api/deploy/run", "/api/password", "/api/users"])
    def test_acoes_exigem_login(self, server, path):
        assert call(server + path, "POST", {})[0] == 401

    def test_session_publica_informa_estado(self, server):
        code, body, _ = call(server + "/api/session")
        assert code == 200 and body == {"user": None, "setup": False}

    def test_pagina_do_app_e_publica(self, server):
        with urllib.request.urlopen(server + "/", timeout=10) as r:
            assert r.status == 200 and b"app" in r.read()

    def test_cookie_seguro(self, server):
        _, raw = web_login(server)
        for flag in ("HttpOnly", "SameSite=Strict", "Secure", "Max-Age=43200", "Path=/"):
            assert flag in raw

    def test_sem_https_nao_marca_secure(self, server):
        code, _, hdr = call(server + "/api/login", "POST", {"user": "chefe", "password": SENHA})
        assert code == 200 and "Secure" not in hdr["Set-Cookie"]

    def test_sessao_e_logout(self, server):
        cook, _ = web_login(server)
        body = call(server + "/api/session", cook=cook)[1]
        assert body["user"]["user"] == "chefe" and body["user"]["role"] == "admin"
        assert call(server + "/api/settings", cook=cook)[0] == 200
        code, _, hdr = call(server + "/api/logout", "POST", {}, cook)
        assert code == 200 and "Max-Age=0" in hdr["Set-Cookie"]
        assert call(server + "/api/settings", cook=cook)[0] == 401  # morreu no servidor, nao so no navegador

    def test_login_errado(self, server):
        code, body, hdr = call(server + "/api/login", "POST", {"user": "chefe", "password": ERRADA})
        assert code == 401 and "incorretos" in body["erro"] and "Set-Cookie" not in hdr

    def test_login_sem_cabecalho_csrf_e_barrado(self, server):
        req = urllib.request.Request(server + "/api/login", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 403

    def test_ip_vem_do_nginx_quando_o_par_e_local(self, server, auth):
        for _ in range(5):
            call(server + "/api/login", "POST", {"user": "chefe", "password": ERRADA}, headers={"X-Real-IP": "5.5.5.5"})
        assert auth.locked_for("5.5.5.5") > 0 and auth.locked_for("127.0.0.1") == 0

    def test_papeis_na_pratica(self, server, auth):
        auth.create_user("leitora", SENHA, "leitor")
        auth.create_user("oper", SENHA, "operador")
        leitora, _ = web_login(server, "leitora")
        oper, _ = web_login(server, "oper")
        assert call(server + "/api/status", cook=leitora)[0] == 200
        assert call(server + "/api/runner/stop", "POST", {}, leitora)[0] == 403
        assert call(server + "/api/kill", "POST", {}, leitora)[0] == 403
        assert call(server + "/api/settings", "POST", {"QUANT_QTY": "0.01"}, oper)[0] == 200
        assert call(server + "/api/deploy/run", "POST", {}, oper)[0] == 403
        assert call(server + "/api/users", cook=oper)[0] == 403
        assert call(server + "/api/audit", cook=oper)[0] == 403

    def test_primeiro_acesso_pelo_navegador(self, tmp_path):
        a = Auth(tmp_path / "novo")
        handler = control.make_handler(tmp_path / "s.json", tmp_path / "K", tmp_path / "r.env", auth=a)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            assert call(base + "/api/session")[1] == {"user": None, "setup": True}
            assert call(base + "/api/status")[0] == 401  # sem usuarios nada abre
            code, body, hdr = call(base + "/api/setup", "POST", {"user": "chefe", "password": SENHA})
            assert code == 200 and body["user"]["role"] == "admin" and "quant_session=" in hdr["Set-Cookie"]
            assert call(base + "/api/setup", "POST", {"user": "x", "password": SENHA})[0] == 409
        finally:
            srv.shutdown()

    def test_login_com_2fa(self, server, auth):
        cook, _ = web_login(server)
        sec = call(server + "/api/2fa/start", "POST", {}, cook)[1]["secret"]
        t = auth.now()
        assert call(server + "/api/2fa/enable", "POST", {"code": authmod.totp_code(sec, int(t // 30))}, cook)[0] == 200
        code, body, _ = call(server + "/api/login", "POST", {"user": "chefe", "password": SENHA})
        assert code == 401 and body["codigo"] is True

    def test_gestao_de_usuarios_pelo_painel(self, server, auth):
        cook, _ = web_login(server)
        code, body, _ = call(server + "/api/users", "POST", {"user": "ana", "password": SENHA, "role": "leitor"}, cook)
        assert code == 200 and body["user"]["role"] == "leitor"
        ana = body["user"]["id"]
        assert call(server + f"/api/users/{ana}/update", "POST", {"role": "operador"}, cook)[0] == 200
        assert call(server + f"/api/users/{ana}/password", "POST", {"password": NOVA}, cook)[0] == 200
        users = call(server + "/api/users", cook=cook)[1]["users"]
        assert {u["user"]: u["role"] for u in users} == {"chefe": "admin", "ana": "operador"}
        assert call(server + f"/api/users/{ana}/delete", "POST", {}, cook)[0] == 200
        eventos = [e["evento"] for e in call(server + "/api/audit", cook=cook)[1]["eventos"]]
        assert "usuario-criado" in eventos and "usuario-apagado" in eventos

    def test_nao_apaga_nem_desativa_a_si_mesmo(self, server):
        cook, _ = web_login(server)
        me = call(server + "/api/session", cook=cook)[1]["user"]["id"]
        assert call(server + f"/api/users/{me}/delete", "POST", {}, cook)[0] == 409
        assert call(server + f"/api/users/{me}/update", "POST", {"disabled": True}, cook)[0] == 409

    def test_acoes_de_operacao_vao_para_a_auditoria(self, server):
        cook, _ = web_login(server)
        call(server + "/api/settings", "POST", {"QUANT_QTY": "0.01"}, cook)
        ev = call(server + "/api/audit", cook=cook)[1]["eventos"]
        assert any(e["evento"] == "acao" and "/api/settings" in e["detalhe"] for e in ev)

    def test_trocar_senha_pelo_painel(self, server, auth):
        cook, _ = web_login(server)
        code, body, _ = call(server + "/api/password", "POST", {"atual": ERRADA, "nova": NOVA}, cook)
        assert code == 400 and "incorreta" in body["erro"]
        code, _, hdr = call(server + "/api/password", "POST", {"atual": SENHA, "nova": NOVA}, cook)
        assert code == 200 and "Max-Age=0" in hdr["Set-Cookie"]
        assert call(server + "/api/status", cook=cook)[0] == 401
        assert auth.login("chefe", NOVA, "3.3.3.3")

    def test_encerrar_outras_sessoes(self, server):
        a, _ = web_login(server)
        b, _ = web_login(server)
        assert call(server + "/api/sessions/revoke-others", "POST", {}, a)[1]["encerradas"] == 1
        assert call(server + "/api/status", cook=b)[0] == 401 and call(server + "/api/status", cook=a)[0] == 200


def test_cli_cria_admin_e_troca_senha(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_AUTH_DIR", str(tmp_path / "d"))
    senhas = iter(["cli-senha-forte-77", "cli-senha-forte-77"])
    monkeypatch.setattr("getpass.getpass", lambda *_: next(senhas))
    assert authmod.main(["set-password", "admin"]) == 0
    a = Auth.from_env(lambda k, d=None: {"QUANT_AUTH_DIR": str(tmp_path / "d")}.get(k, d))
    assert a.login("admin", "cli-senha-forte-77", "1.1.1.1")[2]["role"] == "admin"
    senhas = iter(["outra-senha-forte-88", "outra-senha-forte-88"])
    assert authmod.main(["set-password", "admin"]) == 0
    assert a.login("admin", "outra-senha-forte-88", "1.1.1.1")
    senhas = iter(["cli-senha-forte-77", "diferente-diferente"])
    assert authmod.main(["set-password", "admin"]) == 1
