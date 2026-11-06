"""页面测试使用临时认证桩，不依赖开发者的真实密码。"""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


def authenticated_client():
    client = TestClient(app)
    with patch('app.routers.pages.verify_password', return_value=True):
        response = client.post('/login', data={'username': settings.app_username, 'password': 'test-only-password'})
        assert response.status_code == 200
    return client
