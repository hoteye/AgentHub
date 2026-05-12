from __future__ import annotations


POLICY_QUESTION_MARKERS = (
    "\u5236\u5ea6",
    "\u4f9d\u636e",
    "\u6761\u6b3e",
    "\u529e\u6cd5",
    "\u7ec6\u5219",
    "\u89c4\u7a0b",
    "\u89c4\u8303",
    "\u6d41\u7a0b",
    "\u89c4\u5b9a",
    "\u5ba1\u8ba1\u6574\u6539",
    "\u7ba1\u7406\u8981\u6c42",
)

POLICY_CONTEXT_MARKERS = (
    *POLICY_QUESTION_MARKERS,
    "\u4e3b\u4f9d\u636e",
    "\u573a\u666f\u8865\u5145\u4f9d\u636e",
    "\u8865\u5145\u53c2\u8003",
    "\u8bc1\u636e\u7f3a\u53e3",
    "policy_doc",
    "[e1]",
    "[e2]",
    "[e3]",
)


def looks_like_policy_question(user_text: str) -> bool:
    text = str(user_text or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in POLICY_QUESTION_MARKERS)


def looks_like_policy_context(text: str) -> bool:
    content = str(text or "").strip().lower()
    if not content:
        return False
    return any(marker in content for marker in POLICY_CONTEXT_MARKERS)
