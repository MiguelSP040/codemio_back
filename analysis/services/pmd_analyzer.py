import json
import shlex
import subprocess
from pathlib import Path
from django.conf import settings
from analysis.services.contracts import Analyzer
from analysis.services.types import NormalizedFinding


def _map_pmd_severity(priority: int) -> str:
    if priority <= 1:
        return 'CRITICAL'
    if priority == 2:
        return 'HIGH'
    if priority == 3:
        return 'MEDIUM'
    if priority == 4:
        return 'LOW'
    return 'LOW'


class PmdAnalyzer(Analyzer):
    tool_name = 'pmd'

    def analyze(self, source_dir: Path, workspace_dir: Path) -> list[NormalizedFinding]:
        command = shlex.split(settings.ANALYSIS_PMD_COMMAND) + [
            'check',
            '-d',
            str(source_dir),
            '-R',
            settings.ANALYSIS_PMD_RULESET,
            '-f',
            'json',
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=settings.ANALYSIS_TOOL_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('No se encontró el comando de PMD.') from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('PMD excedió el tiempo máximo de ejecución.') from exc

        if result.returncode not in (0, 4):
            stderr = (result.stderr or '').strip()
            raise RuntimeError(f'PMD terminó con error: {stderr or "sin detalle"}')

        payload = result.stdout.strip() or '{}'
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError('PMD devolvió una salida JSON inválida.') from exc

        findings: list[NormalizedFinding] = []
        for file_item in data.get('files', []):
            filename = file_item.get('filename') or ''
            for violation in file_item.get('violations', []):
                priority = int(violation.get('priority', 5))
                line = violation.get('beginline')
                findings.append(
                    NormalizedFinding(
                        tool=self.tool_name,
                        severity=_map_pmd_severity(priority),
                        rule=str(violation.get('rule') or ''),
                        file_path=str(filename),
                        line=int(line) if line else None,
                        message=str(violation.get('description') or ''),
                    )
                )
        return findings
