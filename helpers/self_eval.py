"""Self-eval stop rule for the explainer.

Stop when the checks pass. Stop when a pass leaves the same failures.
``max_passes`` is only the backstop. Remaining issues are reported.
"""

from __future__ import annotations


def decide(passes: list[dict], max_passes: int) -> str:
    """Return ``run``, ``stop_pass``, ``stop_no_progress``, or ``stop_cap``."""
    if max_passes < 1:
        raise ValueError("max_passes must be at least 1")
    if not passes:
        return "run"
    last = list(passes[-1].get("failures") or [])
    if not last:
        return "stop_pass"
    if len(passes) >= 2 and last == list(passes[-2].get("failures") or []):
        return "stop_no_progress"
    if len(passes) >= max_passes:
        return "stop_cap"
    return "rerender"


def project_note(passes: list[dict], decision: str) -> str:
    lines = ["## Self-eval", ""]
    for index, item in enumerate(passes, start=1):
        failures = list(item.get("failures") or [])
        lines.append(f"Pass {index}: {decision if index == len(passes) else 'rerender'}")
        if not failures:
            lines.append("- checks passed")
        for failure in failures:
            lines.append(f"- {failure}")
        if item.get("loudness"):
            lines.append(f"- loudness: {item['loudness']}")
    if decision != "stop_pass":
        lines.append("")
        lines.append("Remaining issues are listed above. The preview is still shown.")
    return "\n".join(lines) + "\n"
