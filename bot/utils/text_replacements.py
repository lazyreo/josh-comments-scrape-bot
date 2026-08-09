def apply_text_replacements(text: str, rules: list[dict]) -> str:
    """Apply sequential literal replacements; skip empty sources."""
    if not text or not rules:
        return text
    for rule in rules:
        source = rule.get("source") or ""
        if not source:
            continue
        target = rule.get("target")
        if target is None:
            target = ""
        text = text.replace(source, target)
    return text
