from pathlib import Path
import stat
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

    def test_extract_zip_skips_macos_metadata_files(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'macos-metadata.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('__MACOSX/._BadPractices.java', 'not-java-binary')
                archive.writestr('._ComplexClass.java', 'not-java-binary')
                archive.writestr('src/RealClass.java', 'class RealClass {}')

            extracted_count = _extract_zip(zip_path, target_dir)

            self.assertEqual(extracted_count, 1)
            self.assertTrue((target_dir / 'src' / 'RealClass.java').exists())
            self.assertFalse((target_dir / '__MACOSX' / '._BadPractices.java').exists())
            self.assertFalse((target_dir / '._ComplexClass.java').exists())

    def test_extract_zip_rejects_when_only_macos_metadata_files_exist(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'only-metadata.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('__MACOSX/._BadPractices.java', 'not-java-binary')
                archive.writestr('._ComplexClass.java', 'not-java-binary')

            with self.assertRaisesMessage(RuntimeError, 'No se encontraron archivos .java en el ZIP.'):
                _extract_zip(zip_path, target_dir)

    def test_extract_zip_rejects_non_utf8_java_files(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'non-utf8.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('BadEncoding.java', b'\xff\xfe\x00\x00')

            with self.assertRaisesMessage(RuntimeError, 'no son UTF-8 válidos'):
                _extract_zip(zip_path, target_dir)

    def test_extract_zip_skips_common_windows_metadata_files(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'windows-metadata.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('Thumbs.db', 'metadata')
                archive.writestr('desktop.ini', 'metadata')
                archive.writestr('~$draft.java', 'metadata')
                archive.writestr('src/Main.java', 'class Main {}')

            extracted_count = _extract_zip(zip_path, target_dir)

            self.assertEqual(extracted_count, 1)
            self.assertTrue((target_dir / 'src' / 'Main.java').exists())

    def test_extract_zip_rejects_symbolic_links(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'symlink.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            symlink_member = zipfile.ZipInfo('link.java')
            symlink_member.create_system = 3
            symlink_member.external_attr = (stat.S_IFLNK | 0o777) << 16

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr(symlink_member, 'target.java')

            with self.assertRaisesMessage(RuntimeError, 'enlaces simbólicos'):
                _extract_zip(zip_path, target_dir)

    @override_settings(ANALYSIS_MAX_EXTRACTED_FILES=500, ANALYSIS_MAX_EXTRACTED_BYTES=31457280, ANALYSIS_MAX_EXTRACTED_FILE_BYTES=5242880, ANALYSIS_MAX_COMPRESSION_RATIO=2)
    def test_extract_zip_rejects_suspicious_compression_ratio(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'ratio.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            repetitive_content = ('public class A {' + (' int x = 0;' * 5000) + '}').encode('utf-8')
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('A.java', repetitive_content)

            with self.assertRaisesMessage(RuntimeError, 'relación de compresión'):
                _extract_zip(zip_path, target_dir)

    def test_extract_zip_rejects_duplicate_target_paths(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'duplicate-paths.zip'
            target_dir = Path(temp_dir) / 'target'
            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'w') as archive:
                archive.writestr('src/Main.java', 'class Main {}')
                archive.writestr('src/main.java', 'class main {}')

            with self.assertRaisesMessage(RuntimeError, 'rutas duplicadas'):
                _extract_zip(zip_path, target_dir)
