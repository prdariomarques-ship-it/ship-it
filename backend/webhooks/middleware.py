"""Middleware de segurança para validação de webhooks WhatsApp."""

import hashlib
import hmac
import os
from typing import Optional

from fastapi import HTTPException, status, Request


class WebhookSecurity:
    """Validação de assinaturas para webhooks de provedores WhatsApp."""

    @staticmethod
    def validate_evolution(request: Request) -> bool:
        """
        Valida API Key da Evolution API no header 'apikey'.
        
        A Evolution API envia a chave API no header customizado 'apikey'.
        """
        api_key_header = request.headers.get("apikey")
        expected_key = os.getenv("EVOLUTION_API_KEY")
        
        if not expected_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="EVOLUTION_API_KEY não configurada no ambiente"
            )
        
        if not api_key_header or api_key_header != expected_key:
            return False
        
        return True

    @staticmethod
    def validate_official(request: Request, raw_body: bytes) -> bool:
        """
        Valida assinatura HMAC-SHA256 da WhatsApp Official API.
        
        O WhatsApp envia a assinatura no header 'X-Hub-Signature-256'
        no formato: sha256=<hex_signature>
        
        Args:
            request: Objeto FastAPI Request
            raw_body: Body da requisição já lido em bytes
        """
        signature_header = request.headers.get("X-Hub-Signature-256")
        app_secret = os.getenv("WHATSAPP_APP_SECRET")
        
        if not app_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="WHATSAPP_APP_SECRET não configurada no ambiente"
            )
        
        if not signature_header:
            return False
        
        # Extrair hash da assinatura (formato: sha256=<hash>)
        try:
            _, provided_signature = signature_header.split("=", 1)
        except ValueError:
            return False
        
        # Calcular hash esperado do body
        expected_signature = hmac.new(
            app_secret.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(provided_signature, expected_signature)

    @staticmethod
    def validate_openwa(request: Request) -> bool:
        """
        Valida token da OpenWa.
        
        Suporta token via header 'Authorization: Bearer <token>'
        ou query param 'token=<token>'.
        """
        # Tentar header Authorization
        auth_header = request.headers.get("Authorization")
        query_token = request.query_params.get("token")
        expected_token = os.getenv("OPENWA_WEBHOOK_TOKEN")
        
        if not expected_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENWA_WEBHOOK_TOKEN não configurada no ambiente"
            )
        
        provided_token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            provided_token = auth_header[7:]
        elif query_token:
            provided_token = query_token
        
        if not provided_token:
            return False
        
        return hmac.compare_digest(provided_token, expected_token)

    @staticmethod
    def validate_baileys(request: Request) -> bool:
        """
        Validação básica para Baileys.
        
        O Baileys é uma biblioteca cliente que não possui um mecanismo
        oficial de webhook HTTP com assinatura. A segurança deve ser
        garantida por:
        1. Rede privada / VPN
        2. Header customizado compartilhado (ex: X-Baileys-Token)
        3. Restrição de IP
        
        Esta implementação valida um header customizado opcional.
        Se nenhum token for configurado, aceita a requisição (degradação).
        """
        expected_token = os.getenv("BAILEYS_WEBHOOK_TOKEN")
        
        # Se nenhum token estiver configurado, aceitamos (modo desenvolvimento/rede segura)
        if not expected_token:
            return True
        
        provided_token = request.headers.get("X-Baileys-Token")
        
        if not provided_token:
            return False
        
        return hmac.compare_digest(provided_token, expected_token)

    @classmethod
    def validate(cls, provider: str, request: Request, raw_body: bytes) -> bool:
        """
        Dispatch da validação baseada no nome do provider.
        
        Args:
            provider: Nome do provider ('evolution', 'official', 'openwa', 'baileys')
            request: Objeto FastAPI Request
            raw_body: Body da requisição já lido em bytes
            
        Returns:
            bool: True se válido, False se inválido
            
        Raises:
            HTTPException: Se configuração obrigatória estiver faltando
        """
        validators = {
            "evolution": cls.validate_evolution,
            "official": lambda req: cls.validate_official(req, raw_body),
            "openwa": cls.validate_openwa,
            "baileys": cls.validate_baileys,
        }
        
        validator = validators.get(provider.lower())
        
        if not validator:
            # Provider desconhecido: logar e rejeitar
            return False
        
        return validator(request)
