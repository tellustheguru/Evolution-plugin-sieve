import unittest
from unittest.mock import patch

from imap_folders import _list_name, list_folders


class FolderTests(unittest.TestCase):
    def test_decodes_imap_mailbox_names(self):
        self.assertEqual(_list_name(b'(\\HasNoChildren) "/" "Resor/&ANY-"'), 'Resor/Ö')
        self.assertEqual(_list_name(b'(\\HasNoChildren) "/" "A\\\"B"'), 'A"B')

    def test_lists_selectable_mailboxes(self):
        class Connection:
            def login(self, username, password):
                self.credentials = username, password

            def list(self):
                return 'OK', [b'(\\HasNoChildren) "/" "INBOX"',
                              b'(\\Noselect \\HasChildren) "/" "Parent"',
                              b'(\\HasNoChildren) "/" "Archive"']

            def logout(self):
                pass

        connection = Connection()
        with patch('imap_folders.imaplib.IMAP4_SSL', return_value=connection) as create:
            self.assertEqual(list_folders('mail.example', 993, 'user', 'secret',
                                          'ssl-on-alternate-port'), ['Archive', 'INBOX'])
        create.assert_called_once_with('mail.example', 993, timeout=10)
        self.assertEqual(connection.credentials, ('user', 'secret'))


if __name__ == '__main__':
    unittest.main()
