from django.test import SimpleTestCase

from analysis.services.finding_translator import translate_finding_message


class FindingTranslatorTests(SimpleTestCase):
    def test_translates_known_rule(self):
        out = translate_finding_message(
            rule="java:S106",
            message="Replace this use of System.out by a logger.",
        )
        self.assertEqual(out, "Reemplaza el uso de System.out por un logger.")

    def test_translates_pattern_with_variables(self):
        out = translate_finding_message(
            rule="",
            message='File path "a/b/C.java" should match package name "com.demo"',
        )
        self.assertIn('La ruta del archivo "a/b/C.java"', out)
        self.assertIn('"com.demo"', out)

    def test_falls_back_to_quick_replacements(self):
        out = translate_finding_message(
            rule="x",
            message="Potential null pointer in method",
        )
        self.assertIn("Posible referencia nula", out)
