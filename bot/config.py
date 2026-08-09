from typing import Any, Dict, Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyrogram.client import Client

from bot.enums import CaptionVariables


class Config(BaseSettings):
    """Application configuration from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "config.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    API_ID: int
    API_HASH: str
    BOT_TOKEN: str

    DATABASE_NAME: str = "tg_bot"
    DATABASE_URL: Optional[str] = None
    OWNER_ID: int

    RESEND_API_KEY: str
    RESEND_FROM: str

    SLEEP_TIME: int = 10

    CLIENTS: Dict[Any, Any] = Field(default_factory=dict, exclude=True)
    TRANSFERS: Dict[Any, Any] = Field(default_factory=dict, exclude=True)
    ACTIVE_SOURCE_IDS: Set[int] = Field(default_factory=set, exclude=True)


settings = Config()  # type: ignore


class ContextVariables(object):
    BOT: Client | None = None


class Script(object):
    START_MESSAGE = """💾 **Bem-vindo!**

Este bot encaminha mensagens de um chat de **Origem** para um chat de **Destino** usando a sua conta do Telegram conectada. Você também pode receber cópias por e-mail com o Resend.

**Passos simples:**
1. **Entrar** — toque em Conta (ou /account)
2. **Adicionar um encaminhamento** — toque em Encaminhamentos → escolha Origem e Destino
3. Novas mensagens da Origem são copiadas para o Destino com a sua conta

Você também pode colar um link `t.me` para encaminhar a mensagem (se essa Origem tiver um encaminhamento configurado)."""

    RESTART_MESSAGE = "🔄 **O bot está reiniciando. Baixe novamente seus arquivos em andamento em alguns segundos.**"

    HELP_MESSAGE_1 = """**💡 Ajuda**

1. **/account** — Entre com a conta do Telegram que consegue ver a Origem e publicar no Destino.

2. **Encaminhamentos** — toque em Encaminhamentos → Adicionar.
   Envie a Origem (@usuário, id ou uma mensagem encaminhada) e depois o Destino da mesma forma.

3. **Colar um link** — Envie um link `https://t.me/...` para encaminhar aquela mensagem através de um encaminhamento Origem → Destino já configurado.

Precisa de ajuda? Fale com o suporte.
"""

    DEFAULT_CAPTION = "{%s}" % CaptionVariables.CAPTION.value
    PROGRESS_MESSAGE = """**╔══❰ {mode} ❱══❍
║╭━➣
║┣⪼ 📊 **Progresso:** {percentage}%
║┣
║┣⪼ {progress}
║┣
║┣⪼ **Concluído:** {finished} de {total}
║┣
║┣⪼ ⚡ **Velocidade:** {speed}/s
║┣
║┣⪼ ⏰ **Tempo restante:** {eta}
║╰━➣
╚════════════════❍**"""
