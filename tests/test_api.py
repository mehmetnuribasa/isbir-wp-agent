import pytest
from fastapi.testclient import TestClient
from aiChatbot.api.app import createApp
from aiChatbot.models.botConfig import BotConfig
from aiChatbot.services.channelManager import ChannelManager

@pytest.fixture
def test_client():
    config = BotConfig(
        whatsappPhoneNumberId="123",
        whatsappAccessToken="abc",
        whatsappWebhookVerifyToken="test_token"
    )
    channelManager = ChannelManager(config)
    app = createApp(config, channelManager)
    # Using TestClient
    return TestClient(app)

def test_root_endpoint(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["service"] == "İşbir WhatsApp Chatbot"

def test_health_endpoint(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "services" in response.json()

def test_whatsapp_webhook_verify_success(test_client):
    response = test_client.get(
        "/webhook/whatsapp", 
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_token",
            "hub.challenge": "123456789"
        }
    )
    assert response.status_code == 200
    assert response.text == "123456789"

def test_whatsapp_webhook_verify_fail(test_client):
    response = test_client.get(
        "/webhook/whatsapp", 
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "123456789"
        }
    )
    assert response.status_code == 403
