from pathlib import Path
from tempfile import TemporaryDirectory
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
