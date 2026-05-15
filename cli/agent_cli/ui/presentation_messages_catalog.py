from __future__ import annotations

from cli.agent_cli.ui.presentation_messages_catalog_rui import RUI_MESSAGES
from cli.agent_cli.ui.presentation_messages_setup import SETUP_MESSAGES
from cli.agent_cli.ui.presentation_messages_slash import SLASH_MESSAGES
from cli.agent_cli.ui.presentation_messages_status import STATUS_MESSAGES

MESSAGES: dict[str, dict[str, str]] = {
    "app.title": {
        "en": "AgentHub CLI",
        "zh-CN": "AgentHub CLI",
        "ja": "AgentHub CLI",
        "fr": "AgentHub CLI",
    },
    "app.subtitle.base": {
        "en": "Reference-style operator shell",
        "zh-CN": "Reference 风格操作终端",
        "ja": "Reference スタイルのオペレーターシェル",
        "fr": "Shell operateur style Reference",
    },
    "app.subtitle.ready": {
        "en": "Ready",
        "zh-CN": "就绪",
        "ja": "待機中",
        "fr": "Pret",
    },
    "app.subtitle.running": {
        "en": "Running",
        "zh-CN": "运行中",
        "ja": "実行中",
        "fr": "En cours",
    },
    "composer.placeholder": {
        "en": "Ask AgentHub to do anything",
        "zh-CN": "让 AgentHub 处理任何事情",
        "ja": "AgentHub に何でも依頼できます",
        "fr": "Demandez n'importe quoi a AgentHub",
    },
    "composer.image_placeholder": {
        "en": "[Image #{index}]",
        "zh-CN": "[图片 #{index}]",
        "ja": "[画像 #{index}]",
        "fr": "[Image n°{index}]",
    },
    "paste.placeholder.base": {
        "en": "[Pasted Content {char_count} chars]",
        "zh-CN": "[已粘贴内容 {char_count} 字符]",
        "ja": "[貼り付け済みコンテンツ {char_count} 文字]",
        "fr": "[Contenu colle {char_count} caracteres]",
    },
    "paste.placeholder.suffixed": {
        "en": "[Pasted Content {char_count} chars] #{index}",
        "zh-CN": "[已粘贴内容 {char_count} 字符] #{index}",
        "ja": "[貼り付け済みコンテンツ {char_count} 文字] #{index}",
        "fr": "[Contenu colle {char_count} caracteres] #{index}",
    },
    **STATUS_MESSAGES,
    **SETUP_MESSAGES,
    **SLASH_MESSAGES,
    **RUI_MESSAGES,
}
