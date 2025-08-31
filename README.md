# PC-Agent

A lightweight Windows automation demo powered by a multi-agent supervisor that can:
- Launch and control desktop apps (e.g., Calculator)
- Run winget installs with human confirmation
- Query versions (e.g., VS Code)
- Report results back in a structured transcript

## Quick start

```powershell
# in repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python .\crew.py
