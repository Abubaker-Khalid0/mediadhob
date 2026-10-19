# Security and local data

Instagram passwords, cookies, and session IDs grant account access. Keep
`.env`, `cookies.txt`, `ig_session.json`, legacy `cookies.key` / encrypted
cookie files, and logs private. These files are excluded by `.gitignore`.
Downloads and their metadata can reveal personal activity and are excluded too.
Choose a private folder when using a custom download path.

The application reads `.env` from its launch directory. Instagram cookie and
session files are stored there in plaintext for compatibility with yt-dlp and
instagrapi. On POSIX, the application writes these files with owner-only
permissions; on Windows, access follows the directory's Windows permissions.
Store them in a directory accessible only to your account.

Configured credentials and common session fields are redacted from application
log output, but logs may still contain URLs, filenames, and third-party error
messages. Review and redact logs manually before sharing them.

If credentials were ever committed or shared, revoke the affected sessions and
change the exposed credentials first. Deleting a file or adding `.gitignore`
does not remove copies from Git history, forks, or existing downloads.

Report vulnerabilities through the repository's private vulnerability reporting
feature if enabled. Otherwise, ask the maintainer for a private reporting
channel without posting exploit details or credentials in a public issue.
