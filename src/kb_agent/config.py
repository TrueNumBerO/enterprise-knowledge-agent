"""Read project-local credentials without exporting them or echoing values."""
from __future__ import annotations

from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_KEYS = {
    "KB_AGENT_API_KEY", "KB_AGENT_BASE_URL", "KB_AGENT_MODEL", "KB_AGENT_TIMEOUT",
    "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY",
}


class ConfigError(ValueError):
    """Configuration errors must never contain file contents or credentials."""


def load_local_env(path: str | Path | None = None) -> dict[str, str]:
    """Load the project's .env; no shell evaluation, interpolation, or globals.

    Explicitly supplied paths must exist. An absent default file is optional.
    This deliberately supports only the small documented KEY=VALUE format.
    """
    try:
        candidate = Path(path) if path is not None else PROJECT_ROOT / ".env"
        resolved = (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()
        if not resolved.is_relative_to(PROJECT_ROOT):
            raise ConfigError("配置文件路径必须位于项目目录内")
        if path is None and not resolved.exists():
            return {}
        if not resolved.is_file() or resolved.stat().st_size > 16_384:
            raise ConfigError("配置文件不存在、不是普通文件或超过16KB")
        content = resolved.read_text(encoding="utf-8-sig")
    except ConfigError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        raise ConfigError("无法读取本地配置文件，请检查路径、权限和UTF-8编码") from None
    values: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key not in ALLOWED_KEYS:
            raise ConfigError(f"配置文件第{number}行不是受支持的KEY=VALUE配置")
        if key in values:
            raise ConfigError(f"配置文件第{number}行出现重复配置项")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigError(f"配置文件第{number}行引号未闭合")
            value = value[1:-1]
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ConfigError(f"配置文件第{number}行含不支持的控制字符")
        values[key] = value
    return values
