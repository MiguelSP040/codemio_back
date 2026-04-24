from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import zipfile

from django.test import SimpleTestCase, override_settings

from analysis.services.pipeline import _extract_zip


class PipelineZipSecurityTests(SimpleTestCase):
    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=6,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=20.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
    )
    def test_extract_zip_allows_valid_java_and_ignores_non_java(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'ok.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Main.java', 'class Main {}')
                zf.writestr('README.md', '# docs')

            total = _extract_zip(zip_path, target_dir)

            self.assertEqual(total, 1)
            self.assertTrue((target_dir / 'src' / 'Main.java').exists())
            self.assertFalse((target_dir / 'README.md').exists())

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=4,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
    )
    def test_extract_zip_rejects_excessive_path_depth(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'deep.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('a/b/c/d/e/Main.java', 'class Main {}')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('profundidad', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=3.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 512,
    )
    def test_extract_zip_rejects_suspicious_compression_ratio(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'bomb-like.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            repetitive = ('A' * 10000).encode('utf-8')
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Main.java', repetitive)

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('compresión', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
    )
    def test_extract_zip_rejects_symlink_entries(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'symlink.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            symlink_info = zipfile.ZipInfo('src/Main.java')
            symlink_info.create_system = 3
            symlink_info.external_attr = (stat.S_IFLNK | 0o755) << 16
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr(symlink_info, b'/safe/target')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('enlace/sistema', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
        ANALYSIS_MAX_ZIP_ENTRIES=10,
    )
    def test_extract_zip_rejects_nested_zip_entries(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'nested.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Main.java', 'class Main {}')
                zf.writestr('src/evil.zip', b'PK\x03\x04fake')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('ZIP anidados', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
        ANALYSIS_MAX_ZIP_ENTRIES=2,
    )
    def test_extract_zip_rejects_too_many_entries(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'many.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Main.java', 'class Main {}')
                zf.writestr('src/Utils.java', 'class Utils {}')
                zf.writestr('src/Extra.java', 'class Extra {}')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('máximo de entradas', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
        ANALYSIS_MAX_ZIP_ENTRIES=20,
    )
    def test_extract_zip_rejects_windows_style_path_traversal(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'traversal.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(r'..\..\Windows\system32\evil.java', 'class Evil {}')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('ruta insegura', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
        ANALYSIS_MAX_ZIP_ENTRIES=20,
    )
    def test_extract_zip_rejects_java_extension_with_non_java_content(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'fakejava.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Fake.java', 'import os\n\ndef hola():\n    return 1\n')

            with self.assertRaises(RuntimeError) as exc:
                _extract_zip(zip_path, target_dir)
            self.assertIn('no parece código Java', str(exc.exception))

    @override_settings(
        ANALYSIS_MAX_EXTRACTED_FILES=20,
        ANALYSIS_MAX_EXTRACTED_BYTES=1024 * 1024,
        ANALYSIS_MAX_ZIP_PATH_DEPTH=8,
        ANALYSIS_MAX_ZIP_COMPRESSION_RATIO=50.0,
        ANALYSIS_MAX_ZIP_ENTRY_BYTES=1024 * 256,
        ANALYSIS_MAX_ZIP_ENTRIES=20,
    )
    def test_extract_zip_skips_invalid_java_entries_and_keeps_valid_ones(self):
        with TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / 'mixed.zip'
            target_dir = Path(temp_dir) / 'out'
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('src/Good.java', 'class Good {}')
                zf.writestr('src/Fake.java', 'import os\n\ndef hola():\n    return 1\n')

            warnings: list[str] = []
            total = _extract_zip(zip_path, target_dir, validation_warnings=warnings)

            self.assertEqual(total, 1)
            self.assertTrue((target_dir / 'src' / 'Good.java').exists())
            self.assertFalse((target_dir / 'src' / 'Fake.java').exists())
            self.assertTrue(warnings)
            self.assertIn('Fake.java', warnings[0])
