"""Shared paths for the local verification and capture tools; credentials stay in .env."""
from pathlib import Path
from ha_client import ENV
HERE=Path(__file__).resolve().parent
AUDIT=Path(ENV.get('echo_backup_dir') or ((HERE/'.audit_path').read_text().strip() if (HERE/'.audit_path').exists() else HERE/'.backups'))
AUDIT.mkdir(parents=True,exist_ok=True,mode=0o700)
