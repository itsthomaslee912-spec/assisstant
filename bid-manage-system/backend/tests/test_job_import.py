from app.api.jobs import _clean_import_link, _parse_import_line, _parse_import_options


def test_tab_separated_import_line():
    cells = _parse_import_line("Docusign\tLead AI Solutions Delivery Engineer\thttps://example.com/job")
    assert cells == ["Docusign", "Lead AI Solutions Delivery Engineer", "https://example.com/job"]


def test_pipe_separated_import_line_remains_supported():
    cells = _parse_import_line("Docusign | Lead AI Engineer | https://example.com/job | remote")
    assert cells == ["Docusign", "Lead AI Engineer", "https://example.com/job", "remote"]


def test_markdown_job_link_is_normalized():
    value = "[https://example.com/job?jr\\_id=1](https://example.com/job?jr\\_id=1\\&source=list)"
    assert _clean_import_link(value) == "https://example.com/job?jr_id=1&source=list"


def test_applied_status_can_be_fourth_tab_separated_value():
    cells = _parse_import_line("Docusign\tLead AI Engineer\thttps://example.com/job\tApplied")
    assert _parse_import_options(cells) == ("", "applied")


def test_work_model_and_status_can_be_in_either_order():
    assert _parse_import_options(["Acme", "Engineer", "https://example.com", "remote", "applied"]) == ("remote", "applied")
    assert _parse_import_options(["Acme", "Engineer", "https://example.com", "Applied", "hybrid"]) == ("hybrid", "applied")
