"""Configuração do serviço de voz, somente por variáveis de ambiente (sem segredos no código).

O serviço escuta em 127.0.0.1 por padrão e exige token. Nada aqui tem valor de produção.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=None, extra="ignore")

    # --- rede -----------------------------------------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8765

    # --- autenticação: "loja=<token>,twin=<token>". O nome à esquerda é o AGENTE; ele só pode usar o perfil de
    # mesmo nome. Tokens têm no mínimo 32 caracteres. Vazio = o serviço não sobe.
    tokens: str = ""

    # --- motor ----------------------------------------------------------------------------------------------
    # chatterbox | chatterbox_ptbr | elevenlabs | qwen3tts | fake (fake só com allow_fake_engine=true; uso de teste)
    engine: str = "chatterbox"
    allow_fake_engine: bool = False
    device: str = "cpu"  # cpu | cuda | cuda:0 ...
    # Revisão (commit) dos pesos no Hugging Face. Vazio = recusa carregar: não se fixa "main".
    model_revision: str = ""
    model_dir: Path = Path("/models")  # pesos já baixados; o serviço roda com HF_HUB_OFFLINE=1
    # Parâmetros do Chatterbox (valores padrão do upstream; ajuste por escuta/medição no hardware do titular):
    # cfg_weight (0 a 1: aderência ao ritmo/estilo da referência) e exaggeration (0 a 2: expressividade).
    chatterbox_cfg_weight: float = 0.5
    chatterbox_exaggeration: float = 0.5
    chatterbox_pt_br_pack: bool = False  # usa o pacote de língua única pt-BR quando disponível no model_dir
    # Motor `chatterbox_ptbr` (pacote pt-BR oficial: código do Space da Resemble, em ambiente Python separado). A temperatura
    # só existe nele; cfg_weight e exaggeration acima valem para os dois motores Chatterbox. A configuração aprovada por escuta
    # às cegas (17/10/2026, variante C) é cfg=0.3, exaggeration=0.7, temperature=0.8 -- ver docs/EXECUTAR_NO_PC_RTX3060.md.
    ptbr_space_dir: Path | None = None  # pasta do Space baixado (contém chatterbox/src/chatterbox/tts.py)
    chatterbox_temperature: float = 0.8

    # Motor `elevenlabs` (nuvem; o texto sai da máquina). A voz é um voice_id clonado na conta ElevenLabs; a referência local não é usada.
    # Chave: prefira o ARQUIVO (fora do repositório); a variável direta existe para ambientes com secret store.
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_api_key_file: Path | None = None
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_stability: float = 0.4     # menor = mais expressivo/variável; maior = mais monótono
    elevenlabs_similarity: float = 0.8
    elevenlabs_style: float = 0.3         # exagero de estilo; custa latência em alguns modelos
    elevenlabs_speaker_boost: bool = True
    elevenlabs_speed: float = 1.0         # 0.7 a 1.2
    elevenlabs_timeout_seconds: float = 60.0
    elevenlabs_max_retries: int = 2

    @field_validator("elevenlabs_stability", "elevenlabs_similarity", "elevenlabs_style")
    @classmethod
    def _el_unit(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("parâmetros de voz ElevenLabs (stability/similarity/style) devem estar entre 0 e 1")
        return v

    @field_validator("elevenlabs_speed")
    @classmethod
    def _el_speed(cls, v: float) -> float:
        if not 0.7 <= v <= 1.2:
            raise ValueError("elevenlabs_speed deve estar entre 0.7 e 1.2")
        return v

    @field_validator("elevenlabs_max_retries")
    @classmethod
    def _el_retries(cls, v: int) -> int:
        if not 0 <= v <= 5:
            raise ValueError("elevenlabs_max_retries deve estar entre 0 e 5")
        return v

    # --- limites --------------------------------------------------------------------------------------------
    max_text_chars: int = 350
    max_audio_seconds: float = 40.0
    min_audio_seconds: float = 0.4
    max_concurrency: int = 1
    queue_max: int = 4  # além dos que estão gerando; excedeu -> 429
    generation_timeout_seconds: float = 180.0
    result_ttl_seconds: int = 900
    cleanup_interval_seconds: int = 60
    max_request_body_bytes: int = 8192

    # --- armazenamento e perfis -----------------------------------------------------------------------------
    storage_dir: Path = Path("/var/lib/voice-service/tmp")
    profiles_dir: Path = Path("/var/lib/voice-service/profiles")

    # --- saída -----------------------------------------------------------------------------------------------
    opus_bitrate: int = 28000
    target_peak_dbfs: float = -3.0  # só normaliza o pico do ÁUDIO GERADO (nunca a gravação de referência)

    # --- pós-processamento do áudio gerado (tudo desligado por padrão; ver app/postprocess.py) ---------------
    post_compact_pauses: bool = False
    post_tempo: float = 1.0          # 1.0 = sem alteração; 1.12 = 12% mais rápido, mesmo tom
    post_brightness_db: float = 0.0  # 0 = sem alteração; 3 = brilho leve; 6 é forte (chia)

    @field_validator("post_tempo")
    @classmethod
    def _post_tempo(cls, v: float) -> float:
        if not 0.8 <= v <= 1.5:
            raise ValueError("post_tempo deve estar entre 0.8 e 1.5")
        return v

    @field_validator("post_brightness_db")
    @classmethod
    def _post_brightness(cls, v: float) -> float:
        if not 0.0 <= v <= 6.0:
            raise ValueError("post_brightness_db deve estar entre 0 e 6")
        return v

    @field_validator("chatterbox_cfg_weight")
    @classmethod
    def _cfg(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("chatterbox_cfg_weight deve estar entre 0 e 1")
        return v

    @field_validator("chatterbox_exaggeration")
    @classmethod
    def _exg(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("chatterbox_exaggeration deve estar entre 0 e 2")
        return v

    @field_validator("chatterbox_temperature")
    @classmethod
    def _temp(cls, v: float) -> float:
        if not 0.05 <= v <= 2.0:
            raise ValueError("chatterbox_temperature deve estar entre 0.05 e 2")
        return v

    @field_validator("max_concurrency")
    @classmethod
    def _conc(cls, v: int) -> int:
        if v < 1 or v > 8:
            raise ValueError("max_concurrency deve estar entre 1 e 8")
        return v

    @field_validator("queue_max")
    @classmethod
    def _queue(cls, v: int) -> int:
        if v < 0 or v > 64:
            raise ValueError("queue_max deve estar entre 0 e 64")
        return v

    @field_validator("max_text_chars")
    @classmethod
    def _chars(cls, v: int) -> int:
        if v < 20 or v > 2000:
            raise ValueError("max_text_chars deve estar entre 20 e 2000")
        return v

    def token_map(self) -> dict[str, str]:
        """token -> agente. Falha alto se mal formado ou curto: melhor não subir do que subir aberto."""
        mapping: dict[str, str] = {}
        for part in [p.strip() for p in self.tokens.split(",") if p.strip()]:
            if "=" not in part:
                raise ValueError("VOICE_TOKENS: use 'agente=token' separados por vírgula")
            agent, token = (x.strip() for x in part.split("=", 1))
            if not agent.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"VOICE_TOKENS: nome de agente inválido: {agent!r}")
            if len(token) < 32:
                raise ValueError("VOICE_TOKENS: cada token precisa ter ao menos 32 caracteres")
            if token in mapping:
                raise ValueError("VOICE_TOKENS: token repetido para agentes diferentes")
            mapping[token] = agent
        if not mapping:
            raise ValueError("VOICE_TOKENS vazio: o serviço não sobe sem autenticação")
        return mapping


@lru_cache
def get_settings() -> VoiceSettings:
    return VoiceSettings()
