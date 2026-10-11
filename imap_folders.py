"""Read mailbox names from the selected Evolution IMAP account."""

import base64
import imaplib
import re


def _decode_parts(value):
    result = []
    position = 0
    for match in re.finditer(rb'&([A-Za-z0-9+,]*)-', value):
        result.append(value[position:match.start()].decode('utf-8'))
        encoded = match.group(1)
        if encoded:
            data = base64.b64decode(encoded.replace(b',', b'/') + b'=' * (-len(encoded) % 4))
            result.append(data.decode('utf-16-be'))
        else:
            result.append('&')
        position = match.end()
    result.append(value[position:].decode('utf-8'))
    return ''.join(result)


def _list_name(line):
    match = re.match(rb'^\([^)]*\) (?:"(?:[^"\\]|\\.)*"|NIL) (.*)$', line)
    if not match:
        raise ValueError('Ogiltigt IMAP-svar för mapplistan')
    value = match.group(1)
    if value.startswith(b'"') and value.endswith(b'"'):
        value = re.sub(rb'\\(["\\])', rb'\1', value[1:-1])
    return _decode_parts(value)


def list_folders(host, port, username, password, method):
    if method == 'ssl-on-alternate-port':
        connection = imaplib.IMAP4_SSL(host, port or 993, timeout=10)
    elif method == 'starttls-on-standard-port':
        connection = imaplib.IMAP4(host, port or 143, timeout=10)
        connection.starttls()
    else:
        raise ValueError('IMAP-kontot måste använda TLS för att visa mappar')
    try:
        connection.login(username, password)
        status, rows = connection.list()
        if status != 'OK':
            raise ValueError('Kunde inte hämta IMAP-mappar')
        return sorted({_list_name(row) for row in rows
                       if isinstance(row, bytes) and not re.match(rb'^\([^)]*\\Noselect', row, re.I)},
                      key=str.casefold)
    finally:
        connection.logout()
