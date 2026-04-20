from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from analysis.services.java_syntax_metrics import extract_java_syntax_metrics


class JavaSyntaxMetricsTests(SimpleTestCase):
    def test_extract_metrics_counts_structure_and_interclass_calls(self):
        with TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            java_file = source_dir / 'Main.java'
            java_file.write_text(
                (
                    'class Parent {}\n'
                    'interface Worker { void work(); }\n'
                    'class Child extends Parent implements Worker {\n'
                    '  private Helper helper = new Helper();\n'
                    '  public Child(String id) {}\n'
                    '  public void run(int n) { helper.exec(n); }\n'
                    '  public void work() { this.run(1); }\n'
                    '}\n'
                    'class Helper { void exec(int value) {} }\n'
                ),
                encoding='utf-8',
            )

            result = extract_java_syntax_metrics(source_dir)

            self.assertEqual(result.classes_count, 4)
            self.assertEqual(result.methods_count, 5)
            self.assertEqual(result.parameters_count, 3)
            self.assertEqual(result.inheritance_count, 2)
            self.assertEqual(result.interclass_calls_count, 1)
            self.assertEqual(len(result.files), 1)
            self.assertEqual(result.files[0].file_path, 'Main.java')

    def test_extract_metrics_falls_back_to_zero_when_parse_fails(self):
        with TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            broken_file = source_dir / 'Broken.java'
            broken_file.write_text('class Broken { public void a( {', encoding='utf-8')

            result = extract_java_syntax_metrics(source_dir)

            self.assertEqual(len(result.files), 1)
            self.assertEqual(result.files[0].classes_count, 0)
            self.assertEqual(result.methods_count, 0)
