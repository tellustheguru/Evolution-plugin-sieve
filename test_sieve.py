import unittest
from io import BytesIO

from sieve import Client, SieveError, quote


class Stream:
    def __init__(self, data=b''):
        self.input = BytesIO(data)
        self.output = BytesIO()

    def readline(self, size):
        return self.input.readline(size)

    def read(self, size):
        return self.input.read(size)

    def write(self, data):
        return self.output.write(data)


class ClientTests(unittest.TestCase):
    def test_command_injection_is_rejected(self):
        with self.assertRaises(ValueError):
            quote('name\r\nDELETESCRIPT')

    def test_existing_scripts_are_listed_and_read(self):
        client = Client('example.org', 4190, 'user', 'secret')
        client.stream = Stream(b'"first" ACTIVE\r\n"other"\r\nOK\r\n')
        self.assertEqual(client.list_scripts(), [('first', True), ('other', False)])
        client.stream = Stream(b'{5}\r\nhello\r\nOK\r\n')
        self.assertEqual(client.get_script('first'), 'hello')

    def test_oversize_download_is_rejected(self):
        client = Client('example.org', 4190, 'user', 'secret')
        client.stream = Stream(b'{4194305}\r\n')
        with self.assertRaises(SieveError):
            client.get_script('first')

    def test_oversize_upload_is_rejected_before_sending(self):
        client = Client('example.org', 4190, 'user', 'secret')
        client.stream = Stream()
        with self.assertRaises(SieveError):
            client.put_script('first', 'x' * (4 * 1024 * 1024 + 1))
        self.assertEqual(client.stream.output.getvalue(), b'')

    def test_server_error_is_propagated(self):
        client = Client('example.org', 4190, 'user', 'secret')
        client.stream = Stream(b'NO "permission denied"\r\n')
        with self.assertRaises(SieveError):
            client.set_active('first')


if __name__ == '__main__':
    unittest.main()
