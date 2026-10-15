import pytest

from src.ingestion.edgar_client import (
    MissingUserAgentError, get_user_agent, select_filings,
)

SUBS = {"filings": {"recent": {
    "accessionNumber": ["0001-22-000001", "0001-23-000002", "0001-23-000003", "0001-20-000004", "0001-24-000005"],
    "filingDate": ["2022-02-01", "2023-02-01", "2023-05-01", "2020-02-01", "2024-02-01"],
    "reportDate": ["2021-12-31", "2022-12-31", "2023-03-31", "2019-12-31", "2023-12-31"],
    "form": ["10-K", "10-K", "10-Q", "10-K", "10-K/A"],
    "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm", "e.htm"],
}, "files": []}}


def test_select_filters_form_and_date():
    got = select_filings(SUBS, "TEST", 1, "10-K", "2021-01-01")
    assert [f.accession for f in got] == ["0001-22-000001", "0001-23-000002"]


def test_select_respects_end_date():
    got = select_filings(SUBS, "TEST", 1, "10-K", "2021-01-01", "2022-12-31")
    assert len(got) == 1


def test_url_building():
    f = select_filings(SUBS, "TEST", 320193, "10-K", "2021-01-01")[0]
    assert f.url == "https://www.sec.gov/Archives/edgar/data/320193/000122000001/a.htm"


def test_user_agent_rejects_missing_and_placeholder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                      # empty folder: no .env present
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    with pytest.raises(MissingUserAgentError):
        get_user_agent()
    monkeypatch.setenv("EDGAR_USER_AGENT", "Name your.real.email@your-university.edu")
    with pytest.raises(MissingUserAgentError):
        get_user_agent()
    monkeypatch.setenv("EDGAR_USER_AGENT", "Eshika Nahata eshika@iitm.ac.in")
    assert "@" in get_user_agent()


def test_user_agent_read_from_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    (tmp_path / ".env").write_text('EDGAR_USER_AGENT="Test User test.user@university.edu"\n')
    assert get_user_agent() == "Test User test.user@university.edu"