"""AcmeConf config format generator and parser for AcmeCorp benchmarks."""

import os
import random
import re
from copy import deepcopy


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r'^(\d+)(s|m|h)$')
_DURATION_UNITS = {'s': 1, 'm': 60, 'h': 3600}

_VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}')

# Canonical service set (matches logs.py names)
_ALL_SERVICES = ['payments', 'gateway', 'database', 'auth', 'frontend', 'worker']


def _duration_to_seconds(value: str) -> int:
    """Convert duration literal like '30s', '5m', '1h' to integer seconds."""
    m = _DURATION_RE.match(value.strip())
    if m:
        return int(m.group(1)) * _DURATION_UNITS[m.group(2)]
    raise ValueError(f"Invalid duration literal: {value!r}")


def _seconds_to_duration(seconds: int) -> str:
    """Convert integer seconds back to a compact duration literal."""
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _parse_value(raw: str):
    """Parse a single AcmeConf value token into a Python object.

    Returns one of:
      - int
      - int  (duration in seconds)
      - list[str]
      - str  (raw or quoted)
    Variable references (${VAR:-default}) are left as-is for resolve_variables().
    """
    raw = raw.strip()

    # List value: [a, b, c]
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1]
        items = [item.strip().strip('"') for item in inner.split(',') if item.strip()]
        return items

    # Quoted string
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]

    # Variable interpolation (keep as-is, resolved later)
    if _VAR_RE.search(raw):
        return raw

    # Duration literal
    if _DURATION_RE.match(raw):
        return _duration_to_seconds(raw)

    # Integer
    try:
        return int(raw)
    except ValueError:
        pass

    # Unquoted string
    return raw


def _format_value(value) -> str:
    """Format a Python value back into AcmeConf syntax."""
    if isinstance(value, list):
        items = ', '.join(value)
        return f'[{items}]'
    if isinstance(value, int):
        # Could be a duration or a plain int — we use the duration form for
        # values that are multiples of 60 or common durations, but since we
        # store timeouts as seconds we'll just emit the duration notation.
        return _seconds_to_duration(value)
    if isinstance(value, str):
        # Quote strings that contain spaces or special chars, or look like paths
        if ' ' in value or value.startswith('/') or not value.replace('_', '').replace('-', '').isalnum():
            return f'"{value}"'
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_configs(seed: int) -> dict:
    """Generate 3-4 service config files + base.acme deterministically.

    Returns a dict mapping filename → AcmeConf text string.
    """
    rng = random.Random(seed)

    # Pick 3-4 services from the canonical list
    n_services = rng.randint(3, 4)
    services = rng.sample(_ALL_SERVICES, n_services)

    configs = {}

    # base.acme — shared defaults
    base_services = {
        'defaults': {
            'replicas': 2,
            'timeout': 30,
            'health_check': '/healthz',
        }
    }
    configs['base.acme'] = format_acmeconf(base_services, includes=[])

    # Per-service config files
    for service in services:
        deps = [s for s in services if s != service]
        replicas = rng.choice([2, 3, 5])
        timeout_s = rng.choice([15, 30, 60, 120])
        file_services = {
            service: {
                'replicas': f'${{PAYMENTS_REPLICAS:-{replicas}}}' if service == 'payments' else replicas,
                'timeout': timeout_s,
                'deps': deps,
                'health_check': '/healthz',
            }
        }
        filename = f'{service}.acme'
        configs[filename] = format_acmeconf(file_services, includes=['base.acme'])

    return configs


def format_acmeconf(services_dict: dict, includes: list = None) -> str:
    """Render a dict of service definitions into AcmeConf text.

    Args:
        services_dict: mapping of service_name → {field: value}
        includes: list of filenames to emit as @include directives (default: none)

    Returns:
        AcmeConf-formatted string.
    """
    lines = []

    if includes:
        for inc in includes:
            lines.append(f'@include "{inc}"')
        lines.append('')

    for service_name, fields in services_dict.items():
        lines.append(f'service {service_name} {{')
        for field, value in fields.items():
            # Duration fields stored as int seconds → format as duration
            if field == 'timeout' and isinstance(value, int):
                formatted = _seconds_to_duration(value)
            elif isinstance(value, str) and _VAR_RE.search(value):
                # Variable reference — emit as-is
                formatted = value
            else:
                formatted = _format_value(value)
            lines.append(f'  {field} = {formatted}')
        lines.append('}')
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def parse_acmeconf(text: str) -> dict:
    """Parse AcmeConf text into a structured dict.

    Returns:
        {
            "includes": ["base.acme", ...],
            "services": {
                "payments": {
                    "replicas": 3,       # int
                    "timeout": 30,       # int (seconds)
                    "deps": ["a", "b"],  # list
                    "health_check": "/healthz",  # str
                }
            }
        }

    Variable references like ${VAR:-default} are preserved as strings and
    resolved separately by resolve_variables().
    """
    result = {'includes': [], 'services': {}}

    current_service = None
    brace_depth = 0

    for line in text.splitlines():
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            continue

        # @include directive
        if stripped.startswith('@include'):
            m = re.match(r'@include\s+"([^"]+)"', stripped)
            if m:
                result['includes'].append(m.group(1))
            continue

        # Service block open: service name {
        m = re.match(r'^service\s+(\w+)\s*\{', stripped)
        if m:
            current_service = m.group(1)
            result['services'][current_service] = {}
            brace_depth += 1
            continue

        # Block close
        if stripped == '}':
            brace_depth -= 1
            if brace_depth == 0:
                current_service = None
            continue

        # Key = value inside a service block
        if current_service is not None and '=' in stripped:
            key, _, value_raw = stripped.partition('=')
            key = key.strip()
            value_raw = value_raw.strip()
            result['services'][current_service][key] = _parse_value(value_raw)

    return result


def resolve_variables(parsed: dict, env: dict = None) -> dict:
    """Resolve ${VAR:-default} references in a parsed config.

    Args:
        parsed: output of parse_acmeconf()
        env:    optional dict of variable overrides; falls back to os.environ,
                then to the default embedded in the reference.

    Returns:
        A new parsed dict with all variable references replaced by their values.
    """
    effective_env = dict(os.environ)
    if env:
        effective_env.update(env)

    def resolve_str(s: str):
        def replacer(m):
            var_name = m.group(1)
            default = m.group(2)  # may be None
            if var_name in effective_env:
                return effective_env[var_name]
            if default is not None:
                return default
            return m.group(0)  # leave unresolved

        result = _VAR_RE.sub(replacer, s)
        # After substitution, try to re-parse the result
        return _parse_value(result)

    def resolve_value(value):
        if isinstance(value, str) and _VAR_RE.search(value):
            return resolve_str(value)
        return value

    out = deepcopy(parsed)
    for svc_fields in out['services'].values():
        for key, value in svc_fields.items():
            svc_fields[key] = resolve_value(value)
    return out


def diff_configs(config_a_text: str, config_b_text: str) -> list:
    """Compare two AcmeConf texts and return a list of field-level differences.

    Each diff entry is a dict:
        {"service": str, "field": str, "old": any, "new": any}

    Additions (service/field only in B) have old=None.
    Removals (service/field only in A) have new=None.
    Changes have both old and new set.
    """
    a = parse_acmeconf(config_a_text)['services']
    b = parse_acmeconf(config_b_text)['services']

    diffs = []
    all_services = sorted(set(a) | set(b))

    for svc in all_services:
        if svc not in a:
            # Entire service added
            for field, new_val in b[svc].items():
                diffs.append({'service': svc, 'field': field, 'old': None, 'new': new_val})
        elif svc not in b:
            # Entire service removed
            for field, old_val in a[svc].items():
                diffs.append({'service': svc, 'field': field, 'old': old_val, 'new': None})
        else:
            # Service exists in both — compare fields
            all_fields = sorted(set(a[svc]) | set(b[svc]))
            for field in all_fields:
                old_val = a[svc].get(field)
                new_val = b[svc].get(field)
                if field not in a[svc]:
                    diffs.append({'service': svc, 'field': field, 'old': None, 'new': new_val})
                elif field not in b[svc]:
                    diffs.append({'service': svc, 'field': field, 'old': old_val, 'new': None})
                elif old_val != new_val:
                    diffs.append({'service': svc, 'field': field, 'old': old_val, 'new': new_val})

    return diffs


def validate_config(parsed: dict, known_services: list = None) -> list:
    """Validate a parsed config dict and return a list of issue strings.

    Checks:
    - Each service has required fields: replicas, timeout, health_check
    - deps entries reference known services (if known_services is provided)
    """
    required_fields = {'replicas', 'timeout', 'health_check'}
    issues = []

    for svc_name, fields in parsed['services'].items():
        for req in sorted(required_fields):
            if req not in fields:
                issues.append(f"Service '{svc_name}' is missing required field '{req}'")

        if known_services is not None and 'deps' in fields:
            deps = fields['deps']
            if isinstance(deps, list):
                for dep in deps:
                    if dep not in known_services:
                        issues.append(
                            f"Service '{svc_name}' dep '{dep}' is not a known service"
                        )

    return issues
