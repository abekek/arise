"""Tests for benchmarks/acmecorp/logs.py"""

import json
import re

import pytest

from benchmarks.acmecorp.logs import (
    SERVICES,
    SEVERITIES,
    generate_logs,
    ground_truth_ctx_values,
    ground_truth_error_counts,
    ground_truth_errors_by_hour,
    parse_log_line,
    query_logs,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

LOG_RE = re.compile(
    r"^\[ACME:(?P<severity>[A-Z]+):(?P<service>[a-z]+):(?P<timestamp>\d+)\] "
    r"(?P<message>.+?) \| ctx=(?P<ctx>\{.*\})$"
)

START_TS = 1_710_000_000
END_TS = START_TS + 86_400  # 1 day window


@pytest.fixture(scope="module")
def logs_seed42():
    return generate_logs(seed=42, count=500, start_ts=START_TS, end_ts=END_TS)


@pytest.fixture(scope="module")
def logs_seed99():
    return generate_logs(seed=99, count=300, start_ts=START_TS, end_ts=END_TS)


# ── Determinism ───────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_seed_same_output(self):
        a = generate_logs(seed=42, count=200)
        b = generate_logs(seed=42, count=200)
        assert a == b

    def test_different_seeds_differ(self):
        a = generate_logs(seed=1, count=200)
        b = generate_logs(seed=2, count=200)
        assert a != b

    def test_count_respected(self):
        logs = generate_logs(seed=7, count=123)
        assert len(logs) == 123

    def test_default_count(self):
        logs = generate_logs(seed=0)
        assert len(logs) == 500


# ── Format correctness ────────────────────────────────────────────────────────

class TestFormat:
    def test_all_lines_match_pattern(self, logs_seed42):
        for line in logs_seed42:
            assert LOG_RE.match(line), f"Line does not match format: {line!r}"

    def test_severities_are_valid(self, logs_seed42):
        for line in logs_seed42:
            m = LOG_RE.match(line)
            assert m.group("severity") in SEVERITIES

    def test_services_are_valid(self, logs_seed42):
        for line in logs_seed42:
            m = LOG_RE.match(line)
            assert m.group("service") in SERVICES

    def test_timestamps_are_integers(self, logs_seed42):
        for line in logs_seed42:
            m = LOG_RE.match(line)
            ts = m.group("timestamp")
            assert ts.isdigit()

    def test_ctx_is_valid_json(self, logs_seed42):
        for line in logs_seed42:
            m = LOG_RE.match(line)
            ctx = json.loads(m.group("ctx"))
            assert isinstance(ctx, dict)

    def test_sorted_by_timestamp(self, logs_seed42):
        timestamps = []
        for line in logs_seed42:
            m = LOG_RE.match(line)
            timestamps.append(int(m.group("timestamp")))
        assert timestamps == sorted(timestamps)

    def test_timestamps_within_window(self):
        logs = generate_logs(seed=5, count=100, start_ts=START_TS, end_ts=END_TS)
        for line in logs:
            m = LOG_RE.match(line)
            ts = int(m.group("timestamp"))
            assert START_TS <= ts <= END_TS

    def test_all_severity_types_appear(self):
        # With 500 logs and weighted distribution, all severities must appear
        logs = generate_logs(seed=42, count=500)
        found = set()
        for line in logs:
            m = LOG_RE.match(line)
            found.add(m.group("severity"))
        assert found == set(SEVERITIES)

    def test_info_debug_dominate(self, logs_seed42):
        counts = {s: 0 for s in SEVERITIES}
        for line in logs_seed42:
            m = LOG_RE.match(line)
            counts[m.group("severity")] += 1
        total = len(logs_seed42)
        info_debug_pct = (counts["INFO"] + counts["DEBUG"]) / total
        assert info_debug_pct > 0.5, f"Expected INFO+DEBUG > 50%, got {info_debug_pct:.1%}"


# ── parse_log_line ────────────────────────────────────────────────────────────

class TestParseLogLine:
    def test_returns_expected_keys(self, logs_seed42):
        parsed = parse_log_line(logs_seed42[0])
        assert set(parsed.keys()) == {"severity", "service", "timestamp", "message", "ctx"}

    def test_severity_is_string(self, logs_seed42):
        parsed = parse_log_line(logs_seed42[0])
        assert isinstance(parsed["severity"], str)
        assert parsed["severity"] in SEVERITIES

    def test_service_is_string(self, logs_seed42):
        parsed = parse_log_line(logs_seed42[0])
        assert isinstance(parsed["service"], str)
        assert parsed["service"] in SERVICES

    def test_timestamp_is_int(self, logs_seed42):
        parsed = parse_log_line(logs_seed42[0])
        assert isinstance(parsed["timestamp"], int)

    def test_ctx_is_dict(self, logs_seed42):
        parsed = parse_log_line(logs_seed42[0])
        assert isinstance(parsed["ctx"], dict)

    def test_message_is_nonempty_string(self, logs_seed42):
        for line in logs_seed42[:20]:
            parsed = parse_log_line(line)
            assert isinstance(parsed["message"], str) and parsed["message"]

    def test_round_trip_all_lines(self, logs_seed42):
        """parse_log_line must not raise on any generated line."""
        for line in logs_seed42:
            parsed = parse_log_line(line)
            assert parsed["severity"] in SEVERITIES
            assert parsed["service"] in SERVICES

    def test_invalid_line_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_log_line("not a valid log line")

    def test_parse_specific_line(self):
        line = '[ACME:INFO:payments:1710001234] payment processed | ctx={"host":"web-01","region":"us-east-1"}'
        parsed = parse_log_line(line)
        assert parsed["severity"] == "INFO"
        assert parsed["service"] == "payments"
        assert parsed["timestamp"] == 1710001234
        assert parsed["message"] == "payment processed"
        assert parsed["ctx"]["host"] == "web-01"


# ── query_logs ────────────────────────────────────────────────────────────────

class TestQueryLogs:
    def test_no_filter_returns_all(self, logs_seed42):
        result = query_logs(logs_seed42)
        assert result == logs_seed42

    def test_filter_by_service(self, logs_seed42):
        result = query_logs(logs_seed42, service="payments")
        assert len(result) > 0
        for line in result:
            assert parse_log_line(line)["service"] == "payments"

    def test_filter_by_service_excludes_others(self, logs_seed42):
        result = query_logs(logs_seed42, service="auth")
        for line in result:
            assert parse_log_line(line)["service"] == "auth"

    def test_filter_by_severity(self, logs_seed42):
        result = query_logs(logs_seed42, severity="ERROR")
        assert len(result) > 0
        for line in result:
            assert parse_log_line(line)["severity"] == "ERROR"

    def test_filter_by_time_window(self, logs_seed42):
        mid = START_TS + 43200  # noon
        result = query_logs(logs_seed42, start_ts=mid)
        for line in result:
            assert parse_log_line(line)["timestamp"] >= mid

    def test_filter_by_end_ts(self, logs_seed42):
        mid = START_TS + 43200
        result = query_logs(logs_seed42, end_ts=mid)
        for line in result:
            assert parse_log_line(line)["timestamp"] <= mid

    def test_combined_filters(self, logs_seed42):
        mid = START_TS + 43200
        result = query_logs(logs_seed42, service="database", severity="WARN", end_ts=mid)
        for line in result:
            parsed = parse_log_line(line)
            assert parsed["service"] == "database"
            assert parsed["severity"] == "WARN"
            assert parsed["timestamp"] <= mid

    def test_narrow_window_may_return_empty(self, logs_seed42):
        # 1-second window: may legitimately be empty — just verify no crash
        result = query_logs(logs_seed42, start_ts=START_TS, end_ts=START_TS)
        assert isinstance(result, list)

    def test_unknown_service_returns_empty(self, logs_seed42):
        result = query_logs(logs_seed42, service="nonexistent")
        assert result == []

    def test_filter_count_matches_manual_count(self, logs_seed42):
        target_svc = "worker"
        result = query_logs(logs_seed42, service=target_svc)
        manual = [l for l in logs_seed42 if parse_log_line(l)["service"] == target_svc]
        assert result == manual


# ── ground_truth_error_counts ─────────────────────────────────────────────────

class TestGroundTruthErrorCounts:
    def test_returns_dict(self, logs_seed42):
        result = ground_truth_error_counts(logs_seed42)
        assert isinstance(result, dict)

    def test_keys_are_valid_services(self, logs_seed42):
        result = ground_truth_error_counts(logs_seed42)
        for key in result:
            assert key in SERVICES

    def test_values_are_positive_ints(self, logs_seed42):
        result = ground_truth_error_counts(logs_seed42)
        for val in result.values():
            assert isinstance(val, int) and val > 0

    def test_only_error_and_fatal_counted(self, logs_seed42):
        result = ground_truth_error_counts(logs_seed42)
        total = sum(result.values())
        manual_total = sum(
            1 for l in logs_seed42 if parse_log_line(l)["severity"] in ("ERROR", "FATAL")
        )
        assert total == manual_total

    def test_consistent_with_query_logs(self, logs_seed42):
        result = ground_truth_error_counts(logs_seed42)
        for svc, count in result.items():
            errors = query_logs(logs_seed42, service=svc, severity="ERROR")
            fatals = query_logs(logs_seed42, service=svc, severity="FATAL")
            assert count == len(errors) + len(fatals)

    def test_empty_logs(self):
        result = ground_truth_error_counts([])
        assert result == {}


# ── ground_truth_ctx_values ───────────────────────────────────────────────────

class TestGroundTruthCtxValues:
    def test_returns_list(self, logs_seed42):
        result = ground_truth_ctx_values(logs_seed42, "host")
        assert isinstance(result, list)

    def test_values_are_unique(self, logs_seed42):
        result = ground_truth_ctx_values(logs_seed42, "host")
        assert len(result) == len(set(str(v) for v in result))

    def test_known_host_values_present(self, logs_seed42):
        result = ground_truth_ctx_values(logs_seed42, "host")
        # At least some of the known hosts should appear across 500 logs
        assert len(result) > 0

    def test_nonexistent_field_returns_empty(self, logs_seed42):
        result = ground_truth_ctx_values(logs_seed42, "totally_nonexistent_field_xyz")
        assert result == []

    def test_region_values_are_subset_of_known(self, logs_seed42):
        known = {"us-east-1", "us-west-2", "eu-west-1"}
        result = ground_truth_ctx_values(logs_seed42, "region")
        assert set(result).issubset(known)

    def test_empty_logs(self):
        result = ground_truth_ctx_values([], "host")
        assert result == []


# ── ground_truth_errors_by_hour ───────────────────────────────────────────────

class TestGroundTruthErrorsByHour:
    def test_returns_dict(self, logs_seed42):
        result = ground_truth_errors_by_hour(logs_seed42)
        assert isinstance(result, dict)

    def test_keys_are_hour_timestamps(self, logs_seed42):
        result = ground_truth_errors_by_hour(logs_seed42)
        for key in result:
            assert isinstance(key, int)
            assert key % 3600 == 0

    def test_values_are_positive_ints(self, logs_seed42):
        result = ground_truth_errors_by_hour(logs_seed42)
        for val in result.values():
            assert isinstance(val, int) and val > 0

    def test_total_matches_error_count(self, logs_seed42):
        by_hour = ground_truth_errors_by_hour(logs_seed42)
        error_counts = ground_truth_error_counts(logs_seed42)
        assert sum(by_hour.values()) == sum(error_counts.values())

    def test_hour_boundaries_correct(self, logs_seed42):
        by_hour = ground_truth_errors_by_hour(logs_seed42)
        # Manually verify one hour bucket
        for hour, count in by_hour.items():
            manual = sum(
                1 for l in logs_seed42
                if parse_log_line(l)["severity"] in ("ERROR", "FATAL")
                and (parse_log_line(l)["timestamp"] // 3600) * 3600 == hour
            )
            assert count == manual

    def test_empty_logs(self):
        result = ground_truth_errors_by_hour([])
        assert result == {}
