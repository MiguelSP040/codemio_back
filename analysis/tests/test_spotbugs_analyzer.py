import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import SimpleTestCase
from analysis.services.spotbugs_analyzer import SpotBugsAnalyzer


class SpotBugsAnalyzerTests(SimpleTestCase):
    def test_parse_results_uses_specific_source_line_and_not_first_nested(self):
        xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.9.8">
  <BugInstance type="ES_COMPARING_PARAMETER_STRING_WITH_EQ" priority="1">
    <Class classname="TestCalidad">
      <SourceLine classname="TestCalidad" sourcepath="TestCalidad.java" start="9" end="110"/>
    </Class>
    <Method classname="TestCalidad" name="main" signature="([Ljava/lang/String;)V">
      <SourceLine classname="TestCalidad" sourcepath="TestCalidad.java" start="14" end="30"/>
    </Method>
    <SourceLine classname="TestCalidad" sourcepath="TestCalidad.java" start="43" end="43"/>
    <ShortMessage>Comparison of String parameter using == or !=</ShortMessage>
    <LongMessage>Comparison of String parameter using == or !=</LongMessage>
  </BugInstance>
</BugCollection>
"""
        analyzer = SpotBugsAnalyzer()

        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / 'spotbugs.xml'
            xml_path.write_text(xml_payload, encoding='utf-8')
            findings = analyzer._parse_results(xml_path)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.file_path, 'TestCalidad.java')
        self.assertEqual(finding.line, 43)
        self.assertEqual(finding.rule, 'ES_COMPARING_PARAMETER_STRING_WITH_EQ')

    @patch('analysis.services.spotbugs_analyzer.subprocess.run')
    def test_analyze_raises_runtime_error_when_compile_times_out(self, mocked_run):
        mocked_run.side_effect = subprocess.TimeoutExpired(cmd=['javac'], timeout=1)
        analyzer = SpotBugsAnalyzer()
        with TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / 'source'
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / 'Demo.java').write_text('class Demo {}', encoding='utf-8')
            workspace_dir = Path(temp_dir) / 'workspace'
            workspace_dir.mkdir(parents=True, exist_ok=True)

            with self.assertRaisesMessage(RuntimeError, 'compilación para SpotBugs excedió el tiempo máximo'):
                analyzer.analyze(source_dir=source_dir, workspace_dir=workspace_dir)

    @patch('analysis.services.spotbugs_analyzer.subprocess.run')
    def test_analyze_raises_runtime_error_when_spotbugs_times_out(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.CompletedProcess(args=['javac'], returncode=0, stdout='', stderr=''),
            subprocess.TimeoutExpired(cmd=['spotbugs'], timeout=1),
        ]
        analyzer = SpotBugsAnalyzer()
        with TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / 'source'
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / 'Demo.java').write_text('class Demo {}', encoding='utf-8')
            workspace_dir = Path(temp_dir) / 'workspace'
            workspace_dir.mkdir(parents=True, exist_ok=True)

            with self.assertRaisesMessage(RuntimeError, 'SpotBugs excedió el tiempo máximo de ejecución'):
                analyzer.analyze(source_dir=source_dir, workspace_dir=workspace_dir)
