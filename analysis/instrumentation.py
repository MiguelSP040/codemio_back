from __future__ import annotations
import logging
from typing import Any
from django.conf import settings

def analysis_instrumentation_enabled() -> bool:
    return bool(getattr(settings, 'DEBUG_ANALYSIS_INSTRUMENTATION', False))

def digest_prefix(digest: str, n: int = 12) -> str:
    if not digest:
        return ''
    return digest[:n]

def _fmt_val(val: Any) -> str:
    if isinstance(val, bool):
        return 'true' if val else 'false'
    if isinstance(val, float):
        return f'{val:.6g}'
    return str(val)

def analysis_instr_log(target_logger: logging.Logger, event: str, **kwargs: Any) -> None:
    if not analysis_instrumentation_enabled():
        return
    parts = [f'event={event}']
    for key in sorted(kwargs.keys()):
        val = kwargs[key]
        if val is None:
            continue
        s = _fmt_val(val)
        if len(s) > 220:
            s = s[:217] + '...'
        parts.append(f'{key}={s}')
    target_logger.info('analysis_instr | %s', ' | '.join(parts))
