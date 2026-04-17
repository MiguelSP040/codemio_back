from django.test import SimpleTestCase
from analysis.services.pmd_analyzer import _map_pmd_severity


class PmdAnalyzerTests(SimpleTestCase):
    def test_map_pmd_severity_is_normalized(self):
        self.assertEqual(_map_pmd_severity(1), 'CRITICAL')
        self.assertEqual(_map_pmd_severity(2), 'HIGH')
        self.assertEqual(_map_pmd_severity(3), 'MEDIUM')
        self.assertEqual(_map_pmd_severity(4), 'LOW')
        self.assertEqual(_map_pmd_severity(5), 'LOW')
