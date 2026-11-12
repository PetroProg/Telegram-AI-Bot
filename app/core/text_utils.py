import re


def clean_model_response(text: str) -> str:
    """
    Cleans model response by stripping reasoning blocks (<think>...</think>),
    dangling thought tags, and extra chat template artifacts.
    """
    if not text:
        return ""
    # Strip full <think>...</think> tags
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip dangling <think> if model cut off before closing tag
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    # Strip orphaned template/stop tokens
    for token in (
        "</think>",
        "<|im_end|>",
        "<|im_start|>",
        "<|endoftext|>",
        "<|eot_id|>",
        "<|end_of_text|>",
        "<end_of_turn>",
        "<eos>",
    ):
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()
