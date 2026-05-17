import pytest
from pytest_mock import MockerFixture

from agent.alerts import TelegramAlerter


@pytest.mark.asyncio
async def test_telegram_send(mocker: MockerFixture):
    mock_response = mocker.Mock()
    mock_response.raise_for_status = mocker.Mock()
    mock_client = mocker.AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response
    mocker.patch("agent.alerts.httpx.AsyncClient", return_value=mock_client)

    alerter = TelegramAlerter("token123", "chat456")
    ok = await alerter.send("test message")
    assert ok is True
    mock_client.post.assert_called_once()
