from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
from django.test import SimpleTestCase, override_settings
from analysis.services.pipeline import _extract_zip


class PipelineSecurityTests(SimpleTestCase):
    def test_extract_zip_rejects_zip_slip_paths(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'slip.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('../evil.java', 'class Evil {}')

            with self.assertRaisesMessage(RuntimeError, 'ruta insegura'):
                _extract_zip(zip_path, target_dir)

    @override_settings(ANALYSIS_MAX_EXTRACTED_FILES=1, ANALYSIS_MAX_EXTRACTED_BYTES=1000000)
    def test_extract_zip_rejects_when_file_count_exceeds_limit(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'many.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('A.java', 'class A {}')
                archive.writestr('B.java', 'class B {}')

            with self.assertRaisesMessage(RuntimeError, 'número máximo'):
                _extract_zip(zip_path, target_dir)

    @override_settings(ANALYSIS_MAX_EXTRACTED_FILES=500, ANALYSIS_MAX_EXTRACTED_BYTES=10)
    def test_extract_zip_rejects_when_size_exceeds_limit(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'big.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('A.java', 'class A { int x = 123456789; }')

            with self.assertRaisesMessage(RuntimeError, 'tamaño máximo'):
                _extract_zip(zip_path, target_dir)
