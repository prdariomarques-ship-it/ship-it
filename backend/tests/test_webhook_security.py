"""Testes de segurança para webhooks WhatsApp."""

import hashlib
import hmac
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException, status, Request
from fastapi.datastructures import Headers

from webhooks.middleware import WebhookSecurity


class TestWebhookSecurityEvolution:
    """Testes para validação da Evolution API."""

    def test_validate_evolution_success(self):
        """Deve validar com sucesso quando API Key está correta."""
        with patch.dict(os.environ, {"EVOLUTION_API_KEY": "test-api-key-123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"apikey": "test-api-key-123"})
            
            result = WebhookSecurity.validate_evolution(mock_request)
            
            assert result is True

    def test_validate_evolution_wrong_key(self):
        """Deve falhar quando API Key está incorreta."""
        with patch.dict(os.environ, {"EVOLUTION_API_KEY": "test-api-key-123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"apikey": "wrong-key"})
            
            result = WebhookSecurity.validate_evolution(mock_request)
            
            assert result is False

    def test_validate_evolution_missing_header(self):
        """Deve falhar quando header apikey está ausente."""
        with patch.dict(os.environ, {"EVOLUTION_API_KEY": "test-api-key-123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            
            result = WebhookSecurity.validate_evolution(mock_request)
            
            assert result is False

    def test_validate_evolution_missing_config(self):
        """Deve levantar HTTPException quando configuração está ausente."""
        with patch.dict(os.environ, {}, clear=True):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"apikey": "test-api-key-123"})
            
            with pytest.raises(HTTPException) as exc_info:
                WebhookSecurity.validate_evolution(mock_request)
            
            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "EVOLUTION_API_KEY" in exc_info.value.detail


class TestWebhookSecurityOfficial:
    """Testes para validação da WhatsApp Official API."""

    def test_validate_official_success(self):
        """Deve validar com sucesso quando assinatura HMAC está correta."""
        app_secret = "secret123"
        raw_body = b'{"message": "hello"}'
        
        # Calcular assinatura esperada
        expected_signature = hmac.new(
            app_secret.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": app_secret}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({
                "X-Hub-Signature-256": f"sha256={expected_signature}"
            })
            
            result = WebhookSecurity.validate_official(mock_request, raw_body)
            
            assert result is True

    def test_validate_official_wrong_signature(self):
        """Deve falhar quando assinatura está incorreta."""
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "secret123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({
                "X-Hub-Signature-256": "sha256=wrongsignature"
            })
            
            result = WebhookSecurity.validate_official(mock_request, b'{"message": "hello"}')
            
            assert result is False

    def test_validate_official_missing_header(self):
        """Deve falhar quando header de assinatura está ausente."""
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "secret123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            
            result = WebhookSecurity.validate_official(mock_request, b'{"message": "hello"}')
            
            assert result is False

    def test_validate_official_missing_config(self):
        """Deve levantar HTTPException quando configuração está ausente."""
        with patch.dict(os.environ, {}, clear=True):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({
                "X-Hub-Signature-256": "sha256=abc123"
            })
            
            with pytest.raises(HTTPException) as exc_info:
                WebhookSecurity.validate_official(mock_request, b'{"message": "hello"}')
            
            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "WHATSAPP_APP_SECRET" in exc_info.value.detail

    def test_validate_official_invalid_format(self):
        """Deve falhar quando formato da assinatura é inválido."""
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "secret123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({
                "X-Hub-Signature-256": "invalid-format"  # Sem "sha256="
            })
            
            result = WebhookSecurity.validate_official(mock_request, b'{"message": "hello"}')
            
            assert result is False


class TestWebhookSecurityOpenWa:
    """Testes para validação da OpenWa."""

    def test_validate_openwa_via_authorization_header(self):
        """Deve validar via header Authorization: Bearer."""
        with patch.dict(os.environ, {"OPENWA_WEBHOOK_TOKEN": "token123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"Authorization": "Bearer token123"})
            mock_request.query_params = {}
            
            result = WebhookSecurity.validate_openwa(mock_request)
            
            assert result is True

    def test_validate_openwa_via_query_param(self):
        """Deve validar via query param token."""
        with patch.dict(os.environ, {"OPENWA_WEBHOOK_TOKEN": "token123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            mock_request.query_params = {"token": "token123"}
            
            result = WebhookSecurity.validate_openwa(mock_request)
            
            assert result is True

    def test_validate_openwa_wrong_token(self):
        """Deve falhar quando token está incorreto."""
        with patch.dict(os.environ, {"OPENWA_WEBHOOK_TOKEN": "token123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"Authorization": "Bearer wrong-token"})
            mock_request.query_params = {}
            
            result = WebhookSecurity.validate_openwa(mock_request)
            
            assert result is False

    def test_validate_openwa_missing_token(self):
        """Deve falhar quando token está ausente."""
        with patch.dict(os.environ, {"OPENWA_WEBHOOK_TOKEN": "token123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            mock_request.query_params = {}
            
            result = WebhookSecurity.validate_openwa(mock_request)
            
            assert result is False

    def test_validate_openwa_missing_config(self):
        """Deve levantar HTTPException quando configuração está ausente."""
        with patch.dict(os.environ, {}, clear=True):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"Authorization": "Bearer token123"})
            mock_request.query_params = {}
            
            with pytest.raises(HTTPException) as exc_info:
                WebhookSecurity.validate_openwa(mock_request)
            
            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "OPENWA_WEBHOOK_TOKEN" in exc_info.value.detail


class TestWebhookSecurityBaileys:
    """Testes para validação do Baileys."""

    def test_validate_baileys_with_token_success(self):
        """Deve validar com sucesso quando token está correto."""
        with patch.dict(os.environ, {"BAILEYS_WEBHOOK_TOKEN": "baileys-token"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"X-Baileys-Token": "baileys-token"})
            
            result = WebhookSecurity.validate_baileys(mock_request)
            
            assert result is True

    def test_validate_baileys_with_token_failure(self):
        """Deve falhar quando token está incorreto."""
        with patch.dict(os.environ, {"BAILEYS_WEBHOOK_TOKEN": "baileys-token"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"X-Baileys-Token": "wrong-token"})
            
            result = WebhookSecurity.validate_baileys(mock_request)
            
            assert result is False

    def test_validate_baileys_no_token_configured(self):
        """Deve aceitar quando nenhum token está configurado (modo dev)."""
        with patch.dict(os.environ, {}, clear=True):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            
            result = WebhookSecurity.validate_baileys(mock_request)
            
            assert result is True

    def test_validate_baileys_missing_header_when_configured(self):
        """Deve falhar quando token está configurado mas header ausente."""
        with patch.dict(os.environ, {"BAILEYS_WEBHOOK_TOKEN": "baileys-token"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            
            result = WebhookSecurity.validate_baileys(mock_request)
            
            assert result is False


class TestWebhookSecurityDispatch:
    """Testes para o método dispatch validate()."""

    def test_validate_dispatch_evolution(self):
        """Deve dispatchar corretamente para evolution."""
        with patch.dict(os.environ, {"EVOLUTION_API_KEY": "test-key"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"apikey": "test-key"})
            
            result = WebhookSecurity.validate("evolution", mock_request, b'{}')
            
            assert result is True

    def test_validate_dispatch_official(self):
        """Deve dispatchar corretamente para official."""
        app_secret = "secret123"
        raw_body = b'{"message": "hello"}'
        expected_signature = hmac.new(
            app_secret.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": app_secret}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({
                "X-Hub-Signature-256": f"sha256={expected_signature}"
            })
            
            result = WebhookSecurity.validate("official", mock_request, raw_body)
            
            assert result is True

    def test_validate_dispatch_openwa(self):
        """Deve dispatchar corretamente para openwa."""
        with patch.dict(os.environ, {"OPENWA_WEBHOOK_TOKEN": "token123"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"Authorization": "Bearer token123"})
            mock_request.query_params = {}
            
            result = WebhookSecurity.validate("openwa", mock_request, b'{}')
            
            assert result is True

    def test_validate_dispatch_baileys(self):
        """Deve dispatchar corretamente para baileys."""
        with patch.dict(os.environ, {}, clear=True):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({})
            
            result = WebhookSecurity.validate("baileys", mock_request, b'{}')
            
            assert result is True

    def test_validate_unknown_provider(self):
        """Deve retornar False para provider desconhecido."""
        mock_request = MagicMock(spec=Request)
        
        result = WebhookSecurity.validate("unknown_provider", mock_request, b'{}')
        
        assert result is False

    def test_validate_case_insensitive(self):
        """Deve ser case-insensitive para nome do provider."""
        with patch.dict(os.environ, {"EVOLUTION_API_KEY": "test-key"}):
            mock_request = MagicMock(spec=Request)
            mock_request.headers = Headers({"apikey": "test-key"})
            
            # Testar com diferentes cases
            assert WebhookSecurity.validate("EVOLUTION", mock_request, b'{}') is True
            assert WebhookSecurity.validate("Evolution", mock_request, b'{}') is True
            assert WebhookSecurity.validate("evolution", mock_request, b'{}') is True
