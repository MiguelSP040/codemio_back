import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import SimpleTestCase
from analysis.services.pmd_analyzer import _map_pmd_severity
from analysis.services.pmd_analyzer import PmdAnalyzer


class PmdAnalyzerTests(SimpleTestCase):
    def test_map_pmd_severity_is_normalized(self):
        self.assertEqual(_map_pmd_severity(1), 'CRITICAL')
        self.assertEqual(_map_pmd_severity(2), 'HIGH')
        self.assertEqual(_map_pmd_severity(3), 'MEDIUM')
        self.assertEqual(_map_pmd_severity(4), 'LOW')
        self.assertEqual(_map_pmd_severity(5), 'LOW')

    @patch('analysis.services.pmd_analyzer.subprocess.run')
    def test_analyze_raises_runtime_error_on_timeout(self, mocked_run):
        mocked_run.side_effect = subprocess.TimeoutExpired(cmd=['pmd'], timeout=1)
        analyzer = PmdAnalyzer()
        with TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / 'source'
            workspace_dir = Path(temp_dir) / 'workspace'
            source_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir.mkdir(parents=True, exist_ok=True)
            with self.assertRaisesMessage(RuntimeError, 'PMD excedió el tiempo máximo'):
                analyzer.analyze(source_dir=source_dir, workspace_dir=workspace_dir)
