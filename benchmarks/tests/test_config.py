"""Tests for benchmarks/acmecorp/config.py — AcmeConf format."""

import pytest
from benchmarks.acmecorp.config import (
    diff_configs,
    format_acmeconf,
    generate_configs,
    parse_acmeconf,
    resolve_variables,
    validate_config,
)


# ---------------------------------------------------------------------------
# generate_configs
# ---------------------------------------------------------------------------

class TestGenerateConfigs:
    def test_deterministic_same_seed(self):
        a = generate_configs(42)
        b = generate_configs(42)
        assert a == b

    def test_different_seeds_differ(self):
        a = generate_configs(1)
        b = generate_configs(2)
        # Very likely to differ; at minimum keys or content should differ
        assert a != b

    def test_produces_base_acme(self):
        configs = generate_configs(7)
        assert 'base.acme' in configs

    def test_produces_three_to_four_service_files(self):
        configs = generate_configs(7)
        service_files = [k for k in configs if k != 'base.acme']
        assert 3 <= len(service_files) <= 4

    def test_service_files_are_parseable(self):
        configs = generate_configs(99)
        for filename, text in configs.items():
            parsed = parse_acmeconf(text)
            assert isinstance(parsed, dict)
            assert 'services' in parsed
            assert 'includes' in parsed

    def test_service_names_are_canonical(self):
        canonical = {'payments', 'gateway', 'database', 'auth', 'frontend', 'worker'}
        configs = generate_configs(13)
        for filename, text in configs.items():
            parsed = parse_acmeconf(text)
            for svc in parsed['services']:
                assert svc in canonical or svc == 'defaults'


# ---------------------------------------------------------------------------
# format_acmeconf / parse_acmeconf round-trip
# ---------------------------------------------------------------------------

class TestFormatParseRoundTrip:
    def _make_services(self):
        return {
            'payments': {
                'replicas': 3,
                'timeout': 30,   # stored as seconds
                'deps': ['gateway', 'database'],
                'health_check': '/healthz',
            }
        }

    def test_round_trip_preserves_int(self):
        services = self._make_services()
        text = format_acmeconf(services)
        parsed = parse_acmeconf(text)
        assert parsed['services']['payments']['replicas'] == 3

    def test_round_trip_preserves_duration_as_seconds(self):
        services = self._make_services()
        text = format_acmeconf(services)
        parsed = parse_acmeconf(text)
        assert parsed['services']['payments']['timeout'] == 30

    def test_round_trip_preserves_list(self):
        services = self._make_services()
        text = format_acmeconf(services)
        parsed = parse_acmeconf(text)
        assert parsed['services']['payments']['deps'] == ['gateway', 'database']

    def test_round_trip_preserves_string(self):
        services = self._make_services()
        text = format_acmeconf(services)
        parsed = parse_acmeconf(text)
        assert parsed['services']['payments']['health_check'] == '/healthz'

    def test_includes_emitted_and_parsed(self):
        services = self._make_services()
        text = format_acmeconf(services, includes=['base.acme'])
        parsed = parse_acmeconf(text)
        assert 'base.acme' in parsed['includes']

    def test_multiple_services_round_trip(self):
        services = {
            'alpha': {'replicas': 1, 'timeout': 60, 'health_check': '/ping'},
            'beta':  {'replicas': 2, 'timeout': 120, 'health_check': '/ready'},
        }
        text = format_acmeconf(services)
        parsed = parse_acmeconf(text)
        assert set(parsed['services'].keys()) == {'alpha', 'beta'}
        assert parsed['services']['alpha']['timeout'] == 60
        assert parsed['services']['beta']['replicas'] == 2


# ---------------------------------------------------------------------------
# parse_acmeconf value types
# ---------------------------------------------------------------------------

class TestParseValueTypes:
    def _parse(self, text):
        return parse_acmeconf(text)

    def test_integer_value(self):
        text = 'service svc {\n  replicas = 5\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['replicas'] == 5
        assert isinstance(p['services']['svc']['replicas'], int)

    def test_duration_seconds(self):
        text = 'service svc {\n  timeout = 30s\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['timeout'] == 30

    def test_duration_minutes(self):
        text = 'service svc {\n  timeout = 5m\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['timeout'] == 300

    def test_duration_hours(self):
        text = 'service svc {\n  timeout = 1h\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['timeout'] == 3600

    def test_list_value(self):
        text = 'service svc {\n  deps = [a, b, c]\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['deps'] == ['a', 'b', 'c']

    def test_quoted_string(self):
        text = 'service svc {\n  health_check = "/healthz"\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['health_check'] == '/healthz'

    def test_unquoted_string(self):
        text = 'service svc {\n  mode = active\n}\n'
        p = self._parse(text)
        assert p['services']['svc']['mode'] == 'active'

    def test_variable_reference_preserved(self):
        text = 'service svc {\n  replicas = ${REPLICAS:-3}\n}\n'
        p = self._parse(text)
        # Variable should be preserved as string, not resolved
        assert '${REPLICAS:-3}' in str(p['services']['svc']['replicas'])

    def test_include_directive(self):
        text = '@include "base.acme"\nservice svc {\n  replicas = 1\n}\n'
        p = self._parse(text)
        assert p['includes'] == ['base.acme']

    def test_multiple_includes(self):
        text = '@include "base.acme"\n@include "shared.acme"\nservice svc {\n  replicas = 1\n}\n'
        p = self._parse(text)
        assert p['includes'] == ['base.acme', 'shared.acme']


# ---------------------------------------------------------------------------
# resolve_variables
# ---------------------------------------------------------------------------

class TestResolveVariables:
    def _parsed_with_var(self, var_expr='${REPLICAS:-3}', field='replicas'):
        text = f'service svc {{\n  {field} = {var_expr}\n}}\n'
        return parse_acmeconf(text)

    def test_uses_provided_env_dict(self):
        parsed = self._parsed_with_var('${REPLICAS:-3}')
        resolved = resolve_variables(parsed, env={'REPLICAS': '7'})
        assert resolved['services']['svc']['replicas'] == 7

    def test_falls_back_to_default_when_var_absent(self):
        parsed = self._parsed_with_var('${MISSING_VAR_XYZ:-42}')
        resolved = resolve_variables(parsed, env={})
        assert resolved['services']['svc']['replicas'] == 42

    def test_env_overrides_default(self):
        parsed = self._parsed_with_var('${MY_REPLICAS:-1}')
        resolved = resolve_variables(parsed, env={'MY_REPLICAS': '9'})
        assert resolved['services']['svc']['replicas'] == 9

    def test_does_not_mutate_original(self):
        parsed = self._parsed_with_var('${REPLICAS:-3}')
        original_val = parsed['services']['svc']['replicas']
        resolve_variables(parsed, env={'REPLICAS': '99'})
        # Original should still have the variable reference string
        assert parsed['services']['svc']['replicas'] == original_val

    def test_non_variable_values_unchanged(self):
        text = 'service svc {\n  replicas = 5\n  timeout = 30s\n}\n'
        parsed = parse_acmeconf(text)
        resolved = resolve_variables(parsed, env={})
        assert resolved['services']['svc']['replicas'] == 5
        assert resolved['services']['svc']['timeout'] == 30

    def test_string_variable_resolved(self):
        text = 'service svc {\n  health_check = "${HEALTH_PATH:-/healthz}"\n}\n'
        parsed = parse_acmeconf(text)
        resolved = resolve_variables(parsed, env={'HEALTH_PATH': '/ready'})
        assert resolved['services']['svc']['health_check'] == '/ready'

    def test_default_used_when_not_in_env(self):
        parsed = self._parsed_with_var('${TIMEOUT_S:-30}')
        resolved = resolve_variables(parsed, env={})
        # Default "30" should be cast to int via _parse_value
        assert resolved['services']['svc']['replicas'] == 30


# ---------------------------------------------------------------------------
# diff_configs
# ---------------------------------------------------------------------------

class TestDiffConfigs:
    def _text(self, services_dict):
        return format_acmeconf(services_dict)

    def test_no_diff_identical_configs(self):
        text = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h'}})
        assert diff_configs(text, text) == []

    def test_detects_changed_field(self):
        a = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h'}})
        b = self._text({'svc': {'replicas': 5, 'timeout': 30, 'health_check': '/h'}})
        diffs = diff_configs(a, b)
        assert len(diffs) == 1
        assert diffs[0] == {'service': 'svc', 'field': 'replicas', 'old': 2, 'new': 5}

    def test_detects_added_field(self):
        a = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h'}})
        b = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h', 'mode': 'active'}})
        diffs = diff_configs(a, b)
        added = [d for d in diffs if d['field'] == 'mode']
        assert len(added) == 1
        assert added[0]['old'] is None
        assert added[0]['new'] == 'active'

    def test_detects_removed_field(self):
        a = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h', 'mode': 'active'}})
        b = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h'}})
        diffs = diff_configs(a, b)
        removed = [d for d in diffs if d['field'] == 'mode']
        assert len(removed) == 1
        assert removed[0]['old'] == 'active'
        assert removed[0]['new'] is None

    def test_detects_added_service(self):
        a = self._text({'svc_a': {'replicas': 1, 'timeout': 10, 'health_check': '/h'}})
        b = self._text({
            'svc_a': {'replicas': 1, 'timeout': 10, 'health_check': '/h'},
            'svc_b': {'replicas': 2, 'timeout': 20, 'health_check': '/h'},
        })
        diffs = diff_configs(a, b)
        svc_b_diffs = [d for d in diffs if d['service'] == 'svc_b']
        assert len(svc_b_diffs) > 0
        assert all(d['old'] is None for d in svc_b_diffs)

    def test_detects_removed_service(self):
        a = self._text({
            'svc_a': {'replicas': 1, 'timeout': 10, 'health_check': '/h'},
            'svc_b': {'replicas': 2, 'timeout': 20, 'health_check': '/h'},
        })
        b = self._text({'svc_a': {'replicas': 1, 'timeout': 10, 'health_check': '/h'}})
        diffs = diff_configs(a, b)
        svc_b_diffs = [d for d in diffs if d['service'] == 'svc_b']
        assert len(svc_b_diffs) > 0
        assert all(d['new'] is None for d in svc_b_diffs)

    def test_multiple_changes(self):
        a = self._text({'svc': {'replicas': 2, 'timeout': 30, 'health_check': '/h'}})
        b = self._text({'svc': {'replicas': 4, 'timeout': 60, 'health_check': '/h'}})
        diffs = diff_configs(a, b)
        changed_fields = {d['field'] for d in diffs}
        assert 'replicas' in changed_fields
        assert 'timeout' in changed_fields


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def _valid_parsed(self):
        text = (
            'service payments {\n'
            '  replicas = 3\n'
            '  timeout = 30s\n'
            '  health_check = "/healthz"\n'
            '  deps = [gateway]\n'
            '}\n'
        )
        return parse_acmeconf(text)

    def test_valid_config_has_no_issues(self):
        parsed = self._valid_parsed()
        issues = validate_config(parsed, known_services=['payments', 'gateway'])
        assert issues == []

    def test_missing_replicas(self):
        text = 'service svc {\n  timeout = 30s\n  health_check = "/h"\n}\n'
        parsed = parse_acmeconf(text)
        issues = validate_config(parsed)
        assert any('replicas' in i for i in issues)

    def test_missing_timeout(self):
        text = 'service svc {\n  replicas = 2\n  health_check = "/h"\n}\n'
        parsed = parse_acmeconf(text)
        issues = validate_config(parsed)
        assert any('timeout' in i for i in issues)

    def test_missing_health_check(self):
        text = 'service svc {\n  replicas = 2\n  timeout = 30s\n}\n'
        parsed = parse_acmeconf(text)
        issues = validate_config(parsed)
        assert any('health_check' in i for i in issues)

    def test_bad_dep_reference(self):
        parsed = self._valid_parsed()
        # known_services does not include 'gateway'
        issues = validate_config(parsed, known_services=['payments'])
        assert any('gateway' in i for i in issues)

    def test_all_fields_missing(self):
        text = 'service svc {\n  mode = active\n}\n'
        parsed = parse_acmeconf(text)
        issues = validate_config(parsed)
        # All three required fields should be flagged
        assert len(issues) >= 3

    def test_no_known_services_skips_dep_check(self):
        parsed = self._valid_parsed()
        # Without known_services, deps should not be validated
        issues = validate_config(parsed, known_services=None)
        assert issues == []

    def test_multiple_services_validated(self):
        text = (
            'service alpha {\n  replicas = 1\n  timeout = 10s\n  health_check = "/h"\n}\n'
            'service beta {\n  timeout = 10s\n  health_check = "/h"\n}\n'
        )
        parsed = parse_acmeconf(text)
        issues = validate_config(parsed)
        # Only beta should have an issue (missing replicas)
        svc_names = [i for i in issues if 'beta' in i]
        assert len(svc_names) >= 1
        no_alpha_issue = all('alpha' not in i for i in issues)
        assert no_alpha_issue
