# Contributing

Use Python 3.11 or newer and a virtual environment. Install the development
dependencies from the repository root:

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m build
```

The tests use temporary directories and synthetic credentials. They do not
log into Instagram, download media, or require FFmpeg. GitHub Actions runs
them on Windows, macOS, and Linux and checks the built package.

Keep changes focused and describe the behavior changed and the verification
performed in your pull request. Add a regression test for changes to startup,
configuration, authentication file handling, or packaging.

Never include real credentials, cookies, session files, download history, or
raw logs in a commit, issue, screenshot, or test fixture. `.env.example` is the
only environment file intended for source control. Review `git status --short`
and the staged diff before committing. For vulnerability reports, see
[SECURITY.md](SECURITY.md).
