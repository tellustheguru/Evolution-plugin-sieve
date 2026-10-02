import unittest

from sieve_filters import Action, Condition, Filter, parse_document, render_filter


EXAMPLE_SCRIPT = ('require ["fileinto"];\r\n'
             '# rule:[Facebook]\r\n'
             'if allof (header :contains "From" "@facebookmail.com")\r\n'
             '{\r\n fileinto "Facebook";\r\n stop;\r\n}\r\n'
             '# rule:[Important]\r\n'
             'if anyof (address :is "From" "friend@example.org", header :contains "Subject" "Hej")\r\n'
             '{\r\n keep;\r\n stop;\r\n}\r\n')


class SieveFilterTests(unittest.TestCase):
    def test_parses_named_filters_conditions_and_actions(self):
        document = parse_document(EXAMPLE_SCRIPT)
        self.assertEqual([item.name for item in document.filters], ['Facebook', 'Important'])
        self.assertEqual(document.filters[1].join, 'anyof')
        self.assertEqual(len(document.filters[1].conditions), 2)
        self.assertEqual(document.render(), EXAMPLE_SCRIPT)

    def test_edit_preserves_other_filter_exactly(self):
        document = parse_document(EXAMPLE_SCRIPT)
        document.filters[0].actions[0] = Action('fileinto', 'Other')
        document.filters[0].dirty = True
        output = document.render()
        self.assertIn('fileinto "Other";', output)
        self.assertIn(EXAMPLE_SCRIPT.split('# rule:[Important]')[1], output)

    def test_unknown_filter_is_preserved(self):
        script = EXAMPLE_SCRIPT + '# rule:[Vacation]\r\nif true { vacation :days 7 "Away"; }\r\n'
        document = parse_document(script)
        self.assertEqual(len(document.filters), 2)
        self.assertEqual(document.render(), script)

    def test_address_part_modifier_is_not_silently_dropped(self):
        script = 'if address :domain :is "From" "example.org" { keep; }\n'
        document = parse_document(script)
        self.assertEqual(document.filters, [])
        self.assertEqual(document.render(), script)

    def test_invalid_copy_tag_is_not_treated_as_editable(self):
        script = 'if true { reject :copy "No"; }\n'
        document = parse_document(script)
        self.assertEqual(document.filters, [])
        self.assertEqual(document.render(), script)

    def test_nested_condition_in_else_chain_is_not_detached(self):
        script = ('if header :is "Subject" "A" { keep; } else {\n'
                  'if header :is "Subject" "B" { discard; }\n}\n')
        document = parse_document(script)
        self.assertEqual(document.filters, [])
        self.assertEqual(document.render(), script)

    def test_multiline_text_is_preserved_without_parsing_inner_if(self):
        script = ('require "vacation";\n'
                  'vacation text:\n'
                  'if header :is "Subject" "fake" { discard; }\n'
                  '.\n;\n')
        document = parse_document(script)
        self.assertEqual(document.filters, [])
        self.assertEqual(document.render(), script)

    def test_disabled_filter(self):
        script = '# rule:[Disabled]\r\nif false # header :contains "Subject" "X"\r\n{\r\n discard;\r\n}\r\n'
        document = parse_document(script)
        self.assertEqual(len(document.filters), 1)
        self.assertFalse(document.filters[0].enabled)
        self.assertEqual(document.render(), script)

    def test_render_requires_extension(self):
        document = parse_document('')
        document.parts.append(Filter('Archive', conditions=[Condition('header', 'Subject', 'contains', 'Invoice')],
                                     actions=[Action('fileinto', 'Archive')], dirty=True))
        output = document.render()
        self.assertIn('require ["fileinto"];', output)
        self.assertIn('fileinto "Archive";', output)

    def test_unchanged_script_is_byte_identical_even_without_require(self):
        script = '# rule:[Existing]\nif header :contains "Subject" "X"\n{\n fileinto "Folder";\n}\n'
        self.assertEqual(parse_document(script).render(), script)

    def test_flag_action_adds_required_capability_when_edited(self):
        document = parse_document('# rule:[Flag]\nif exists "From" { keep; }\n')
        document.filters[0].actions = [Action('addflag', '\\Seen')]
        document.filters[0].dirty = True
        self.assertIn('require ["imap4flags"]', document.render())

    def test_unnamed_client_filter_is_graphically_editable(self):
        script = 'require ["fileinto"];\nif header :contains "Subject" "Invoice" { fileinto "Bills"; }\n'
        document = parse_document(script)
        self.assertEqual(len(document.filters), 1)
        document.filters[0].actions[0] = Action('fileinto', 'Archive')
        document.filters[0].dirty = True
        self.assertIn('fileinto "Archive";', document.render())

    def test_body_and_simple_vacation_filter(self):
        script = 'require ["body", "vacation"];\nif body :contains "holiday" { vacation "Away"; }\n'
        document = parse_document(script)
        self.assertEqual(document.filters[0].conditions[0].kind, 'body')
        self.assertEqual(document.filters[0].actions[0].kind, 'vacation')
        self.assertEqual(document.render(), script)


if __name__ == '__main__':
    unittest.main()
