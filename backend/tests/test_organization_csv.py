"""Strict production CSV intake preserves quoted names and rejects unsafe census shapes."""

import csv
from io import StringIO

import pytest
from test_organization_fixtures import NOW, envelope, example_config, example_records

from otm.organization.csv_feed import CsvFeedError, parse_csv
from otm.organization.reconcile import prepare


# Serialize fictional rows with no employee ID, retaining the exact supported CSV headings.
def csv_bytes(records=None):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["EMPLOYEE_FULL_NAME", "EMAIL", "MGR", "TOP_MGR"])
    for record in records if records is not None else example_records():
        writer.writerow(
            [
                record.full_name,
                record.email,
                record.manager_email or "",
                record.reported_top_manager_email or "",
            ]
        )
    return stream.getvalue().encode()


# CSV quoting, BOM, normalized emails and absent optional manager hints remain lossless.
def test_csv_quotes_unicode_and_email_identity():
    content = (
        "\ufeffEMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\r\n"
        '"Élodie, Example", ELODIE@EXAMPLE.TEST ,boss@example.test,\r\n'
    )
    rows = parse_csv(content.encode())
    assert rows[0].full_name == "Élodie, Example"
    assert rows[0].source_record_id == "email:elodie@example.test"
    assert rows[0].reported_top_manager_email is None


# Malformed, empty, oversized and ambiguous inputs cannot become absence evidence.
@pytest.mark.parametrize(
    "content",
    [
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,EMAIL,TOP_MGR\nx,a@example.test,b@example.test,\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nx,not-email,,\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nx,a@example.test,,,extra\n",
        b'EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n"unterminated',
        b"\xff\xfe",
        b"\0",
        b"x" * (2 * 1024 * 1024 + 1),
    ],
)
def test_csv_rejects_unsafe_source_shapes(content):
    with pytest.raises(CsvFeedError):
        parse_csv(content)


# Repeated identities cannot be silently deduplicated into a smaller apparent census.
def test_csv_duplicate_normalized_email_rejected():
    with pytest.raises(CsvFeedError, match="Duplicate employee"):
        parse_csv(csv_bytes((example_records()[0], example_records()[0])))


# Honor the root-profile exemption without weakening missing-manager census gates.
def test_configured_boundary_can_be_omitted_but_other_managers_cannot():
    config = example_config(required_root_profile=False)
    rows = example_records()[1:]
    candidate = prepare(rows, envelope(), config, None, NOW)
    assert candidate.absence_eligible
    missing = prepare(rows[1:], envelope(), config, None, NOW)
    assert not missing.absence_eligible
    assert any(d.code == "MANAGER_PROFILE_MISSING" for d in missing.diagnostics)


# Conflicting top managers create review evidence while manager paths determine the LOB.
def test_top_manager_hint_is_checked_without_overriding_graph():
    rows = tuple(
        r.model_copy(update={"reported_top_manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    candidate = prepare(rows, envelope(), example_config(), None, NOW)
    assert ("TOP_MANAGER_MISMATCH", "engineer@example.test") in candidate.issues
    assert next(p for p in candidate.people if p.email == "engineer@example.test").lob_id == "one"
    leader_rows = tuple(
        r.model_copy(update={"reported_top_manager_email": "root@example.test"})
        if r.email == "one@example.test"
        else r
        for r in example_records()
    )
    leader = prepare(leader_rows, envelope(), example_config(), None, NOW)
    assert not any(kind == "TOP_MANAGER_MISMATCH" for kind, _ in leader.issues)


# Blank physical rows are ignored and header order/case do not change canonical employee facts.
def test_csv_header_order_blank_lines_and_whitespace():
    rows = parse_csv(
        b" email , top_mgr , mgr , employee_full_name\n\n , , , \n"
        b"NEW@EXAMPLE.TEST,one@example.test,one@example.test,New Engineer\n"
    )
    assert len(rows) == 1 and rows[0].email == "new@example.test"
    assert rows[0].manager_email == rows[0].reported_top_manager_email == "one@example.test"


# Census input is bounded before graph construction; crossing the row cap is an explicit error.
def test_csv_rejects_more_than_five_thousand_rows():
    content = "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n" + "".join(
        f"Engineer {index},engineer{index}@example.test,one@example.test,one@example.test\n"
        for index in range(5001)
    )
    with pytest.raises(CsvFeedError, match="5,000"):
        parse_csv(content.encode())


# Local readers take only the bounded byte window, then share exactly the transport parser.
def test_bounded_csv_reader(tmp_path):
    from otm.organization.csv_feed import read_csv

    path = tmp_path / "organization.csv"
    path.write_bytes(csv_bytes())
    assert read_csv(path) == parse_csv(csv_bytes())
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(CsvFeedError, match="2 MiB"):
        read_csv(path)


# Equal content is a new delivery; callers retain an existing intake for a transport retry.
def test_each_csv_intake_has_a_fresh_delivery_identity_and_stable_content_hash():
    from otm.organization.csv_feed import csv_intake

    policy = example_config().policy
    first, digest = csv_intake(csv_bytes(), policy, captured_at=NOW, complete=True)
    repeated, same_digest = csv_intake(csv_bytes(), policy, captured_at=NOW, complete=True)
    assert first.records == repeated.records
    assert first.envelope.external_snapshot_id != repeated.envelope.external_snapshot_id
    assert digest == same_digest
    assert digest in first.envelope.external_snapshot_id
    assert first.envelope.source_id == policy.source_id
    assert first.envelope.population_id == policy.population_id
    assert first.envelope.captured_at == NOW
    assert first.envelope.declared_completeness == "complete"
    retry = first.model_validate_json(first.model_dump_json())
    assert retry.envelope.external_snapshot_id == first.envelope.external_snapshot_id
    partial, _ = csv_intake(csv_bytes(), policy, captured_at=None, complete=False)
    assert partial.envelope.captured_at is None
    assert partial.envelope.declared_completeness == "partial"


# Keep the manual CSV sequence importable through qualified absence, return and root repair.
def test_manual_mapping_runbook_csv_sequence():
    from datetime import timedelta
    from pathlib import Path

    from test_organization_fixtures import envelope
    from test_organization_reconcile import revision

    from otm.organization.contracts import Lob
    from otm.organization.reconcile import prepare

    root = Path(__file__).resolve().parents[2] / "docs/how-to/organization-mapping"
    config = example_config().model_copy(
        update={
            "lobs": (
                Lob(
                    id="alpha",
                    label="Alpha",
                    leader_email="alpha@example.test",
                    designee_emails=("delegate@example.test",),
                ),
                Lob(id="beta", label="Beta", leader_email="beta@example.test"),
            )
        }
    )
    previous = None
    for index, file in enumerate(sorted(root.glob("*.csv"))):
        records = parse_csv(file.read_bytes())
        if index == 4:
            config = config.model_copy(
                update={
                    "policy": config.policy.model_copy(
                        update={"root_email": "successor@example.test"}
                    ),
                    "lobs": (
                        config.lobs[0].model_copy(
                            update={
                                "leader_email": "acting.alpha@example.test",
                                "designee_emails": (),
                            }
                        ),
                        config.lobs[1],
                    ),
                }
            )
        at = NOW + timedelta(minutes=index)
        result = prepare(records, envelope(key=str(index), capture=at), config, previous, at)
        assert not result.rejected and result.absence_eligible, file.name
        if index == 2:
            assert next(
                p for p in result.people if p.email == "engineer@example.test"
            ).absence_review
        if index == 4:
            assert next(p for p in result.people if p.email == "root@example.test").absence_review
            assert (
                next(p for p in result.people if p.email == "manager@example.test").ancestry
                == "resolved"
            )
        previous = revision(result)
    assert index == 5
