from django.test import SimpleTestCase
from analysis.services.message_catalog import get_message_es


class MessageCatalogTests(SimpleTestCase):
    def test_returns_translated_message_when_rule_exists(self):
        translated = get_message_es(
            tool='spotbugs',
            rule='DM_NUMBER_CTOR',
            default_message='Method invokes inefficient Number constructor; use static valueOf instead',
        )
        self.assertEqual(translated, 'Se invoca un constructor ineficiente de Number; usa valueOf().')

    def test_returns_default_message_when_rule_not_in_catalog(self):
        default_message = 'Unknown external analyzer message'
        translated = get_message_es(
            tool='spotbugs',
            rule='UNKNOWN_RULE',
            default_message=default_message,
        )
        self.assertEqual(translated, default_message)

    def test_returns_default_message_for_unknown_tool(self):
        default_message = 'Generic analyzer message'
        translated = get_message_es(
            tool='other-tool',
            rule='ANY_RULE',
            default_message=default_message,
        )
        self.assertEqual(translated, default_message)

    def test_returns_translated_message_for_new_spotbugs_rules(self):
        translated = get_message_es(
            tool='spotbugs',
            rule='NP_ALWAYS_NULL',
            default_message='Null pointer dereference',
        )
        self.assertEqual(translated, 'Posible desreferenciación de puntero nulo.')
