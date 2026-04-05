from __future__ import annotations


def classify_stage_error(*, returncode: int, stderr: str, stdout: str) -> str:
    if int(returncode) == 0:
        return "NONE"

    text = f"{stderr}\n{stdout}".lower()
    if "no data available" in text or "csv not found" in text:
        return "DATA_MISSING"
    if "unrecognized arguments" in text or "required when" in text:
        return "ARGUMENT_ERROR"
    if "modulenotfounderror" in text or "missing python dependency" in text:
        return "DEPENDENCY_ERROR"
    if "filenotfounderror" in text:
        return "FILE_NOT_FOUND"
    return "RUNTIME_ERROR"
