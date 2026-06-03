import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.sync_awesome_md import RepoRef, filter_repos, parse_awesome_repos


SAMPLE_README = """
- [Python](https://github.com/vinta/awesome-python#readme)
- [Node.js](https://github.com/sindresorhus/awesome-nodejs#readme)
- [Python again](https://github.com/vinta/awesome-python#readme)
- [MCP](https://github.com/example/awesome-mcp/tree/main#readme)
"""


def test_parse_awesome_repos_deduplicates():
    repos = parse_awesome_repos(SAMPLE_README)
    slugs = [r.slug for r in repos]
    assert slugs.count("vinta/awesome-python") == 1
    assert "sindresorhus/awesome-nodejs" in slugs
    assert "example/awesome-mcp" in slugs


def test_parse_awesome_repos_skips_sponsors():
    readme = """
    [Sponsor](https://github.com/sponsors/sindresorhus)
    [Python](https://github.com/vinta/awesome-python#readme)
    """
    repos = parse_awesome_repos(readme)
    slugs = [r.slug for r in repos]
    assert "sponsors/sindresorhus" not in slugs
    assert "vinta/awesome-python" in slugs


def test_filter_repos():
    repos = [
        RepoRef("vinta", "awesome-python"),
        RepoRef("sindresorhus", "awesome-nodejs"),
    ]
    filtered = filter_repos(repos, "python")
    assert len(filtered) == 1
    assert filtered[0].repo == "awesome-python"
