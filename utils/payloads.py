"""Attack payloads for defensive security tests against our own UAT app.

The tests assert that the application REJECTS/SANITISES these inputs
(no SQL error surfaced, no script execution) - they are not attack tools.
"""

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users;--",
    "' OR 1=1--",
    "admin'--",
    "' UNION SELECT NULL--",
    "1' AND SLEEP(5)--",
    '" OR ""="',
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert('xss')>",
    "<svg/onload=alert('xss')>",
    '"><script>alert(1)</script>',
    "javascript:alert('xss')",
]

# if any of these appear in the rendered page, an unhandled DB error likely leaked
SQL_ERROR_SIGNS = [
    "sql syntax", "sqlstate", "odbc", "ora-", "mysql", "psql",
    "unclosed quotation", "syntax error near", "stack trace",
]
