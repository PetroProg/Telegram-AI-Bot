import html
import re


def clean_model_response(text: str) -> str:
    """
    Cleans model response by stripping reasoning blocks (<think>...</think>,
    <thought>...</thought>, <|thought>...</thought|>), dangling thought tags,
    and extra chat template artifacts.
    """
    if not text:
        return ""
    # Strip full <think>...</think> and <thought>...</thought> blocks
    cleaned = re.sub(
        r"<(?:\|)?(?:think|thought)(?:\|)?>.*?</(?:\|)?(?:think|thought)(?:\|)?>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip Gemma 4 / turn-based reasoning blocks: <|turn>thought ... (up to <|turn>model or <turn|>)
    cleaned = re.sub(
        r"<(?:start_of_turn|\|turn)>thought\b.*?(?:<(?:start_of_turn|\|turn)>model\s*|<turn\|>|<end_of_turn>)",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # If a closing </think> or </thought> appears without an opening tag (e.g. prompt pre-opened it),
    # strip everything up to and including the closing tag
    cleaned = re.sub(
        r"^.*?</(?:\|)?(?:think|thought)(?:\|)?>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip standalone leading <thought> or <think> tags (or dangling blocks if no answer follows)
    cleaned = re.sub(r"^\s*<(?:\|)?(?:think|thought)(?:\|)?>\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<(?:\|)?(?:think|thought)(?:\|)?>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip leaked turn headers (e.g. <start_of_turn>model, <|turn>model, <|start_header_id|>assistant<|end_header_id|>)
    cleaned = re.sub(r"<\|start_header_id\|>(?:system|user|assistant)<\|end_header_id\|>\s*", "", cleaned)
    cleaned = re.sub(r"<(?:start_of_turn|\|turn)>(?:system|user|model|thought)\s*", "", cleaned)
    # Strip orphaned template/stop tokens
    for token in (
        "</think>",
        "<think>",
        "</thought>",
        "<thought>",
        "<|thought|>",
        "<|thought>",
        "<thought|>",
        "<|im_end|>",
        "<|im_start|>",
        "<|endoftext|>",
        "<|eot_id|>",
        "<|end_of_text|>",
        "<end_of_turn>",
        "<start_of_turn>",
        "<|turn>",
        "<turn|>",
        "<eos>",
    ):
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


def markdown_to_html(text: str) -> str:
    """
    Converts common LLM Markdown output into Telegram-safe HTML.
    Protects fenced code blocks and inline code before formatting prose.
    """
    if not text:
        return ""

    placeholders: list[str] = []

    def _stash(value: str) -> str:
        idx = len(placeholders)
        placeholders.append(value)
        return f"\x00PH{idx}\x00"

    def _replace_fenced_code(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code = html.escape(match.group(2).strip("\n"))
        if lang and re.match(r"^[A-Za-z0-9_+-]+$", lang):
            return _stash(f'<pre><code class="language-{lang}">{code}</code></pre>')
        return _stash(f"<pre><code>{code}</code></pre>")

    def _replace_inline_code(match: re.Match) -> str:
        code = html.escape(match.group(1))
        return _stash(f"<code>{code}</code>")

    # 1. Extract fenced code blocks and inline code
    result = re.sub(r"```([^\n`]*)\n(.*?)```", _replace_fenced_code, text, flags=re.DOTALL)
    result = re.sub(r"`([^`\n]+)`", _replace_inline_code, result)

    # 2. Escape remaining HTML characters
    result = html.escape(result, quote=False)

    # 3. Markdown links [text](url)
    result = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        result,
    )

    # 4. Headings (# .. ######)
    result = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", result, flags=re.MULTILINE)

    # 5. Bullet lists (- or * at line start) before italic parsing
    result = re.sub(r"^[ \t]*[-*]\s+", "• ", result, flags=re.MULTILINE)

    # 6. Bold (**text** or __text__), Strikethrough (~~text~~), Italic (*text*)
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result, flags=re.DOTALL)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result, flags=re.DOTALL)
    result = re.sub(r"~~(.+?)~~", r"<s>\1</s>", result, flags=re.DOTALL)
    result = re.sub(
        r"(?<!\*)\*([^\s*][^*]*?[^\s*]|[^\s*])\*(?!\*)",
        r"<i>\1</i>",
        result,
    )

    # 7. Restore code blocks
    for idx, value in enumerate(placeholders):
        result = result.replace(f"\x00PH{idx}\x00", value)

    return result
