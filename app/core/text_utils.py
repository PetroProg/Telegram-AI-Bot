import re


def clean_model_response(text: str) -> str:
    """
    Cleans model response by stripping reasoning blocks (<think>...</think>),
    dangling thought tags, and extra formatting artifacts.
    """
    if not text:
        return ""
    # Strip full <think>...</think> tags
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip dangling <think> if model cut off before closing tag
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    # Strip any orphaned tags
    cleaned = cleaned.replace("</think>", "").replace("<|im_end|>", "").replace("<|endoftext|>", "")
    return cleaned.strip()
