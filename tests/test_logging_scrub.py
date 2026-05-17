import io
import json
import logging

import structlog

from agent.logging_setup import scrub_secrets


def test_scrub_secrets_redacts_private_key():
    secret = "0x" + "a" * 64
    event = {"message": f"key={secret}", "AGENT_PRIVATE_KEY": secret}
    cleaned = scrub_secrets(None, "", event)
    assert secret not in json.dumps(cleaned)
    assert cleaned["AGENT_PRIVATE_KEY"] == "***REDACTED***"


def test_private_key_never_in_log_output():
    secret = "0x" + "b" * 64
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    structlog.configure(
        processors=[
            scrub_secrets,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buf),
    )
    log = structlog.get_logger()
    log.info("wallet_loaded", AGENT_PRIVATE_KEY=secret, note=f"using {secret}")
    output = buf.getvalue()
    assert secret not in output
