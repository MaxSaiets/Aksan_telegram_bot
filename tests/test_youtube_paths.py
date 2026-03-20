from pathlib import Path


def test_project_file_resolves_repo_root():
    from app.services.youtube_uploader import _project_file, _token_file

    project_file = _project_file("client_secrets.json")
    token_file = _token_file()

    assert project_file.name == "client_secrets.json"
    assert token_file.name == "token.json"
    assert project_file.parent == token_file.parent
    assert project_file.parent == Path(__file__).resolve().parents[1]
