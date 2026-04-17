import shlex
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from django.conf import settings
from analysis.services.contracts import Analyzer
from analysis.services.types import NormalizedFinding


def _map_spotbugs_severity(priority: int) -> str:
    if priority <= 1:
        return 'CRITICAL'
    if priority == 2:
        return 'HIGH'
    if priority == 3:
        return 'MEDIUM'
    return 'LOW'


class SpotBugsAnalyzer(Analyzer):
    tool_name = 'spotbugs'

    def analyze(self, source_dir: Path, workspace_dir: Path) -> list[NormalizedFinding]:
        java_files = [str(path) for path in source_dir.rglob('*.java')]
        if not java_files:
            return []

        classes_dir = workspace_dir / 'classes'
        classes_dir.mkdir(parents=True, exist_ok=True)
        compile_cmd = shlex.split(settings.ANALYSIS_JAVAC_COMMAND) + ['-d', str(classes_dir)] + java_files

        try:
            compile_result = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=settings.ANALYSIS_TOOL_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('No se encontró el comando javac.') from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('La compilación para SpotBugs excedió el tiempo máximo.') from exc

        if compile_result.returncode != 0:
            stderr = (compile_result.stderr or '').strip()
            raise RuntimeError(f'No se pudo compilar el código para SpotBugs: {stderr or "sin detalle"}')

        output_path = workspace_dir / 'spotbugs.xml'
        spotbugs_cmd = shlex.split(settings.ANALYSIS_SPOTBUGS_COMMAND) + [
            '-textui',
            '-xml:withMessages',
            '-output',
            str(output_path),
            str(classes_dir),
        ]

        try:
            result = subprocess.run(
                spotbugs_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=settings.ANALYSIS_TOOL_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('No se encontró el comando de SpotBugs.') from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('SpotBugs excedió el tiempo máximo de ejecución.') from exc

        if result.returncode not in (0, 1):
            stderr = (result.stderr or '').strip()
            raise RuntimeError(f'SpotBugs terminó con error: {stderr or "sin detalle"}')

        return self._parse_results(output_path)

    def _parse_results(self, output_path: Path) -> list[NormalizedFinding]:
        if not output_path.exists():
            return []
        try:
            root = ET.parse(output_path).getroot()
        except ET.ParseError as exc:
            raise RuntimeError('SpotBugs devolvió un XML inválido.') from exc

        findings: list[NormalizedFinding] = []
        for bug in root.findall('BugInstance'):
            priority = int(bug.attrib.get('priority', '3'))
            rule = bug.attrib.get('type', '')
            source_line = self._pick_source_line(bug)
            file_path = self._extract_file_path(source_line)
            line_attr = source_line.attrib.get('start') if source_line is not None else None
            message_node = bug.find('LongMessage') or bug.find('ShortMessage')
            message = (message_node.text or '').strip() if message_node is not None else ''
            findings.append(
                NormalizedFinding(
                    tool=self.tool_name,
                    severity=_map_spotbugs_severity(priority),
                    rule=rule,
                    file_path=file_path,
                    line=int(line_attr) if line_attr else None,
                    message=message,
                )
            )
        return findings

    @staticmethod
    def _pick_source_line(bug: ET.Element) -> ET.Element | None:
        direct = bug.find('SourceLine')
        if direct is not None and direct.attrib.get('start'):
            return direct

        default_role = bug.find(".//SourceLine[@role='SOURCE_LINE_DEFAULT']")
        if default_role is not None and default_role.attrib.get('start'):
            return default_role

        all_lines = bug.findall('.//SourceLine')
        for item in all_lines:
            if item.attrib.get('start'):
                return item

        return direct or default_role or (all_lines[0] if all_lines else None)

    @staticmethod
    def _extract_file_path(source_line: ET.Element | None) -> str:
        if source_line is None:
            return ''
        return source_line.attrib.get('sourcepath') or source_line.attrib.get('sourcefile') or ''
