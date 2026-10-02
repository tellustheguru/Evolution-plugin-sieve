"""Small ManageSieve client using verified STARTTLS."""

import base64
import re
import socket
import ssl


class SieveError(Exception):
    pass


class AuthenticationError(SieveError):
    pass


def quote(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError("Ogiltiga tecken i textfält")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _unquote(value):
    return re.sub(r'\\([\\"])', r'\1', value)


class Client:
    def __init__(self, host, port, username, password, timeout=10):
        self.host, self.port = host, int(port)
        self.username, self.password = username, password
        self.timeout = timeout
        self.sock = self.stream = None
        self.capabilities = {}

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.stream = self.sock.makefile("rwb", buffering=0)
        try:
            self.capabilities = self._capabilities()
            if "STARTTLS" not in self.capabilities:
                raise SieveError("Servern erbjuder inte STARTTLS")
            self._send("STARTTLS")
            self._expect_ok()
            self.stream.close()
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
            self.stream = self.sock.makefile("rwb", buffering=0)
            self.capabilities = self._capabilities()
            if "PLAIN" not in self.capabilities.get("SASL", "").upper().split():
                raise SieveError("Servern erbjuder inte SASL PLAIN")
            auth = base64.b64encode(("\0" + self.username + "\0" + self.password).encode()).decode()
            self._send('AUTHENTICATE "PLAIN" ' + quote(auth))
            try:
                self._expect_ok()
            except SieveError as error:
                raise AuthenticationError(str(error)) from error
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        try:
            if self.stream:
                self.stream.close()
        finally:
            if self.sock:
                self.sock.close()
            self.stream = self.sock = None

    def _line(self):
        data = self.stream.readline(1024 * 1024 + 1)
        if not data or len(data) > 1024 * 1024 or not data.endswith(b"\r\n"):
            raise SieveError("Ogiltigt eller avbrutet svar från servern")
        return data[:-2].decode("utf-8")

    def _send(self, command):
        self.stream.write(command.encode("utf-8") + b"\r\n")

    def _expect_ok(self):
        line = self._line()
        if line == "OK" or line.startswith("OK "):
            return line
        raise SieveError(line)

    def _capabilities(self):
        result = {}
        for _ in range(100):
            line = self._line()
            if line == "OK" or line.startswith("OK "):
                return result
            if line.startswith("NO") or line.startswith("BYE"):
                raise SieveError(line)
            match = re.fullmatch(r'"([A-Za-z0-9-]+)"(?: "((?:[^"\\]|\\.)*)")?', line)
            if not match:
                raise SieveError("Ogiltiga serveregenskaper: " + line)
            result[match.group(1).upper()] = _unquote(match.group(2) or "")
        raise SieveError("För många serveregenskaper")

    def list_scripts(self):
        self._send("LISTSCRIPTS")
        scripts = []
        for _ in range(1000):
            line = self._line()
            if line == "OK" or line.startswith("OK "):
                return scripts
            if line.startswith("NO") or line.startswith("BYE"):
                raise SieveError(line)
            match = re.fullmatch(r'"((?:[^"\\]|\\.)*)"( ACTIVE)?', line)
            if not match:
                raise SieveError("Ogiltig skriptlista: " + line)
            scripts.append((_unquote(match.group(1)), bool(match.group(2))))
        raise SieveError("För många skript på servern")

    def get_script(self, name):
        self._send("GETSCRIPT " + quote(name))
        marker = self._line()
        match = re.fullmatch(r'\{([0-9]+)\+?\}', marker)
        if not match:
            raise SieveError(marker)
        size = int(match.group(1))
        if size > 4 * 1024 * 1024:
            raise SieveError("Skriptet är för stort")
        chunks = []
        remaining = size
        while remaining:
            chunk = self.stream.read(remaining)
            if not chunk:
                raise SieveError("Ofullständigt skript")
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != size or self.stream.read(2) != b"\r\n":
            raise SieveError("Ofullständigt skript")
        self._expect_ok()
        return data.decode("utf-8")

    def put_script(self, name, script):
        data = script.encode("utf-8")
        if len(data) > 4 * 1024 * 1024:
            raise SieveError("Skriptet är för stort")
        self._send("PUTSCRIPT " + quote(name) + f" {{{len(data)}+}}")
        self.stream.write(data + b"\r\n")
        self._expect_ok()

    def set_active(self, name):
        self._send("SETACTIVE " + quote(name))
        self._expect_ok()
