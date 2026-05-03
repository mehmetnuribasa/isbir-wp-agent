"""System configuration data models with Pydantic validation."""

import os
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict


class ServerConfig(BaseModel):
    """Minimal server configuration."""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    debug: bool = Field(default=True, description="Debug mode")

    @property
    def webhookBaseUrl(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def whatsappWebhookUrl(self) -> str:
        return f"{self.webhookBaseUrl}/webhook/whatsapp"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level",
    )
    format: str = Field(
        default="json",
        pattern="^(json|text)$",
        description="Logging format",
    )
    enableCorrelationIds: bool = Field(
        default=True,
        description="Enable correlation IDs in logs",
    )


class WhatsAppConfig(BaseModel):
    """WhatsApp configuration."""

    phoneNumberId: str = Field(default="", description="WhatsApp phone number ID")
    accessToken: str = Field(default="", description="WhatsApp access token")
    webhookVerifyToken: str = Field(
        default="", description="WhatsApp webhook verify token"
    )
    apiVersion: str = Field(default="v21.0", description="WhatsApp API version")


class BotConfig(BaseSettings):
    """System configuration with environment variable loading."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Gemini AI Studio configuration
    geminiApiKey: str = Field(
        default="",
        description="Gemini AI Studio API Key",
        validation_alias=AliasChoices(
            "GEMINI_API_KEY", "geminiApiKey"
        ),
    )

    # WhatsApp configuration
    whatsappPhoneNumberId: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WHATSAPP_PHONE_NUMBER_ID", "whatsappPhoneNumberId"
        ),
    )
    whatsappAccessToken: str = Field(
        default="",
        validation_alias=AliasChoices("WHATSAPP_ACCESS_TOKEN", "whatsappAccessToken"),
    )
    whatsappWebhookVerifyToken: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "whatsappWebhookVerifyToken"
        ),
    )
    whatsappApiVersion: str = Field(
        default="v21.0",
        validation_alias=AliasChoices(
            "WHATSAPP_API_VERSION", "whatsappApiVersion"
        ),
    )

    # Server configuration
    serverHost: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("SERVER_HOST", "serverHost"),
    )
    serverPort: int = Field(
        default=8000,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("SERVER_PORT", "serverPort"),
    )
    serverDebug: bool = Field(
        default=True,
        validation_alias=AliasChoices("SERVER_DEBUG", "serverDebug"),
    )

    # Knowledge configuration
    knowledgeBasePath: str = Field(
        default="data/knowledge-base.txt",
        validation_alias=AliasChoices("KNOWLEDGE_BASE_PATH", "knowledgeBasePath"),
    )


    chromaDbPath: str = Field(
        default="data/chroma_db",
        description="ChromaDB persistent storage path",
        validation_alias=AliasChoices("CHROMA_DB_PATH", "chromaDbPath"),
    )

    # Logging configuration
    logLevel: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        validation_alias=AliasChoices("LOG_LEVEL", "logLevel"),
    )
    logFormat: str = Field(
        default="json",
        pattern="^(json|text)$",
        validation_alias=AliasChoices("LOG_FORMAT", "logFormat"),
    )
    logEnableCorrelationIds: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "LOG_ENABLE_CORRELATION_IDS", "logEnableCorrelationIds"
        ),
    )

    # Environment
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "environment"),
    )

    # Message Queue configuration
    queueMaxSize: int = Field(
        default=1000,
        validation_alias=AliasChoices("QUEUE_MAX_SIZE", "queueMaxSize"),
    )
    queueWorkerCount: int = Field(
        default=3,
        ge=1,
        validation_alias=AliasChoices("QUEUE_WORKER_COUNT", "queueWorkerCount"),
    )
    queueProcessingTimeout: int = Field(
        default=60,
        validation_alias=AliasChoices("QUEUE_PROCESSING_TIMEOUT", "queueProcessingTimeout"),
    )

    # Rate limiting
    maxRequestsPerMinute: int = Field(
        default=30,
        validation_alias=AliasChoices("MAX_REQUESTS_PER_MINUTE", "maxRequestsPerMinute"),
    )
    userMessageDebounceSeconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices("USER_MESSAGE_DEBOUNCE_SECONDS", "userMessageDebounceSeconds"),
    )

    # PostgreSQL Database (Milestone 6)
    databaseUrl: str = Field(
        default="",
        description="PostgreSQL async connection URL (postgresql+asyncpg://...)",
        validation_alias=AliasChoices("DATABASE_URL", "databaseUrl"),
    )
    databaseEcho: bool = Field(
        default=False,
        description="SQLAlchemy SQL query logging (debug only)",
        validation_alias=AliasChoices("DATABASE_ECHO", "databaseEcho"),
    )

    @property
    def whatsappConfig(self) -> WhatsAppConfig:
        return WhatsAppConfig(
            phoneNumberId=self.whatsappPhoneNumberId,
            accessToken=self.whatsappAccessToken,
            webhookVerifyToken=self.whatsappWebhookVerifyToken,
            apiVersion=self.whatsappApiVersion,
        )

    @property
    def serverConfig(self) -> ServerConfig:
        return ServerConfig(
            host=self.serverHost,
            port=self.serverPort,
            debug=self.serverDebug,
        )

    @property
    def loggingConfig(self) -> LoggingConfig:
        return LoggingConfig(
            level=self.logLevel,
            format=self.logFormat,
            enableCorrelationIds=self.logEnableCorrelationIds,
        )

    def validateConfiguration(self) -> None:
        """Validate required configuration."""
        errors = []

        if not self.geminiApiKey:
            errors.append("GEMINI_API_KEY must be set")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        class _CustomEnvSource(EnvSettingsSource):
            def prepare_field_value(
                self, name, field, value, value_is_complex
            ):
                return super().prepare_field_value(
                    name, field, value, value_is_complex
                )

        return (
            init_settings,
            _CustomEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


def loadBotConfig() -> BotConfig:
    """Load and validate bot configuration from environment variables."""

    try:
        config = BotConfig()  # type: ignore[call-arg]
        config.validateConfiguration()
        return config
    except Exception as exc:
        raise ValueError(f"Failed to load configuration: {exc}") from exc
