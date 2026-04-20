from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from analysis.services.sonar_runtime_service import (
    _build_config,
    _fetch_issues,
    _sanitize_secret_text,
    run_sonar_analysis,
)


class SonarRuntimeServiceTests(SimpleTestCase):
    @override_settings(
        SONAR_HOST_URL='https://sonarcloud.io',
        SONAR_TOKEN='token',
        SONAR_ORGANIZATION='',
        SONAR_ORG='fallback-org',
        SONAR_SCANNER_COMMAND='sonar-scanner',
        SONAR_API_TIMEOUT_SECONDS=10,
        SONAR_QUALITYGATE_TIMEOUT_SECONDS=10,
    )
    def test_build_config_supports_sonar_org_alias(self):
        config = _build_config()
        self.assertEqual(config.organization, 'fallback-org')

    @override_settings(
        SONAR_HOST_URL='https://sonarcloud.io',
        SONAR_TOKEN='token',
        SONAR_ORGANIZATION='org',
        SONAR_SCANNER_COMMAND='sonar-scanner',
        SONAR_API_TIMEOUT_SECONDS=10,
        SONAR_QUALITYGATE_TIMEOUT_SECONDS=10,
        ANALYSIS_TOOL_TIMEOUT_SECONDS=30,
    )
    @patch('analysis.services.sonar_runtime_service.subprocess.run')
    @patch('analysis.services.sonar_runtime_service.urlopen')
    def test_run_sonar_analysis_maps_metrics_and_issues(self, urlopen_mock, run_mock):
        captured_properties: dict[str, str] = {}

        def _scanner_side_effect(*args, **kwargs):
            scanner_args = args[0]
            settings_arg = next(str(arg) for arg in scanner_args if str(arg).startswith('-Dproject.settings='))
            properties_path = Path(settings_arg.split('=', 1)[1])
            captured_properties['content'] = properties_path.read_text(encoding='utf-8')
            return MagicMock(returncode=0, stderr='', stdout='')

        run_mock.side_effect = _scanner_side_effect

        issues_response = MagicMock()
        issues_response.__enter__.return_value.read.return_value = (
            b'{"paging":{"total":1},"issues":[{"severity":"MAJOR","rule":"java:S106","component":"org_key_1:src/Main.java","message":"Avoid println","type":"CODE_SMELL","textRange":{"startLine":10}}]}'
        )
        metrics_response = MagicMock()
        metrics_response.__enter__.return_value.read.return_value = (
            b'{"component":{"measures":[{"metric":"bugs","value":"1"},{"metric":"vulnerabilities","value":"0"},{"metric":"code_smells","value":"4"},{"metric":"complexity","value":"7"},{"metric":"duplicated_lines_density","value":"2.1"},{"metric":"coverage","value":"75.5"},{"metric":"ncloc","value":"150"},{"metric":"alert_status","value":"OK"}]}}'
        )
        urlopen_mock.side_effect = [issues_response, metrics_response]

        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / 'source'
            source.mkdir(parents=True, exist_ok=True)
            (source / 'Main.java').write_text('class Main {}', encoding='utf-8')
            out = run_sonar_analysis(
                source_dir=source,
                workspace_dir=workspace,
                project_key='org_key_1',
                source_name='Main.java',
            )

        self.assertEqual(len(out.findings), 1)
        self.assertEqual(out.findings[0].severity, 'MEDIUM')
        self.assertEqual(out.findings[0].file_path, 'src/Main.java')
        self.assertEqual(out.metrics.quality_gate_status, 'FAILED')
        self.assertEqual(out.metrics.code_smells, 4)
        scanner_args = run_mock.call_args.args[0]
        self.assertTrue(any(str(arg).startswith('-Dproject.settings=') for arg in scanner_args))
        self.assertFalse(any('sonar.token=' in str(arg) for arg in scanner_args))
        self.assertEqual(run_mock.call_args.kwargs['env']['SONAR_TOKEN'], 'token')
        generated_properties = captured_properties.get('content', '')
        self.assertIn('sonar.inclusions=**/*.java', generated_properties)
        self.assertIn('sonar.exclusions=**/*.zip', generated_properties)
        self.assertIn('sonar.qualitygate.wait=false', generated_properties)
        self.assertNotIn('sonar.qualitygate.wait=true', generated_properties)

    @override_settings(
        SONAR_HOST_URL='https://sonarcloud.io',
        SONAR_TOKEN='token',
        SONAR_ORGANIZATION='org',
        SONAR_API_TIMEOUT_SECONDS=10,
    )
    @patch('analysis.services.sonar_runtime_service.urlopen')
    def test_fetch_issues_paginates_and_normalizes_fields(self, urlopen_mock):
        page_one = MagicMock()
        page_one.__enter__.return_value.read.return_value = (
            b'{"paging":{"total":501},"issues":[{"severity":"BLOCKER","rule":"java:S1","component":"proj:src/A.java","message":"A","type":"BUG","effort":"1 h 10 min","textRange":{"startLine":3}}]}'
        )
        page_two = MagicMock()
        page_two.__enter__.return_value.read.return_value = b'{"paging":{"total":501},"issues":[]}'
        urlopen_mock.side_effect = [page_one, page_two]

        config = _build_config()
        findings = _fetch_issues(project_key='proj', config=config)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, 'CRITICAL')
        self.assertEqual(findings[0].file_path, 'src/A.java')
        self.assertEqual(findings[0].effort_minutes, 70)
        self.assertEqual(urlopen_mock.call_count, 2)

    @override_settings(
        SONAR_HOST_URL='https://sonarcloud.io',
        SONAR_TOKEN='token',
        SONAR_ORGANIZATION='org',
        SONAR_SCANNER_COMMAND='sonar-scanner',
        SONAR_API_TIMEOUT_SECONDS=10,
        SONAR_QUALITYGATE_TIMEOUT_SECONDS=10,
        ANALYSIS_TOOL_TIMEOUT_SECONDS=30,
    )
    @patch('analysis.services.sonar_runtime_service.subprocess.run')
    @patch('analysis.services.sonar_runtime_service.urlopen')
    def test_run_sonar_analysis_api_error_hides_credentials(self, urlopen_mock, run_mock):
        run_mock.return_value = MagicMock(returncode=0, stderr='', stdout='')
        urlopen_mock.side_effect = RuntimeError('SonarCloud API respondió 401.')

        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / 'source'
            source.mkdir(parents=True, exist_ok=True)
            (source / 'Main.java').write_text('class Main {}', encoding='utf-8')
            with self.assertRaises(RuntimeError) as exc:
                run_sonar_analysis(
                    source_dir=source,
                    workspace_dir=workspace,
                    project_key='org_key_1',
                    source_name='Main.java',
                )

        self.assertNotIn('token', str(exc.exception).lower())

    def test_sanitize_secret_text_masks_token_patterns(self):
        raw = 'Authorization=abc123 token:abc123 other'
        safe = _sanitize_secret_text(raw, token='abc123')
        self.assertNotIn('abc123', safe)
        self.assertIn('Authorization=***', safe)
