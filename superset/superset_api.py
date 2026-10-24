"""Клиент REST API Superset на стандартной библиотеке (requests в venv нет)."""

import http.cookiejar
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8088"


class Superset:
    def __init__(self, username: str, password: str):
        self.token = None
        self.csrf = None
        # CSRF-токен привязан к сессионной cookie, поэтому её нужно хранить.
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.login(username, password)

    def _request(self, method: str, path: str, payload=None):
        url = BASE + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if self.csrf:
            req.add_header("X-CSRFToken", self.csrf)
        try:
            with self.opener.open(req, timeout=120) as resp:
                body = resp.read().decode()
                return resp.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, {"raw": body}

    def login(self, username: str, password: str):
        status, body = self._request("POST", "/api/v1/security/login", {
            "username": username, "password": password,
            "provider": "db", "refresh": True,
        })
        if status != 200:
            raise RuntimeError(f"login failed: {status} {body}")
        self.token = body["access_token"]
        status, body = self._request("GET", "/api/v1/security/csrf_token/")
        if status != 200:
            raise RuntimeError(f"csrf failed: {status} {body}")
        self.csrf = body["result"]

    def get(self, path):
        return self._request("GET", path)

    def get_raw(self, path):
        """Возвращает (status, bytes) для бинарных выгрузок вроде экспорта ZIP.

        Читать тело нужно внутри `with`: при выходе из блока ответ
        закрывается, и поток уже отдаёт пустые данные.
        """
        req = urllib.request.Request(BASE + path, method="GET")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self.opener.open(req, timeout=120) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path, payload):
        return self._request("POST", path, payload)

    def put(self, path, payload):
        return self._request("PUT", path, payload)
