SYSTEM_INSTRUCTION = (
    "You are a precise, helpful document analysis assistant integrated into "
    "JazzyVault, a secure document vault product. You only respond based on "
    "the document text provided to you. Be concise and well-structured. "
    "Never invent facts not present in the document."
)


def build_prompt(request_type: str, document_text: str, target_language: str | None = None) -> str:
    if request_type == "summarize":
        return (
            "Summarize the following document in a clear, concise way. "
            "Aim for 3-6 sentences unless the document is very long, in "
            "which case a short paragraph is fine. Capture the main points "
            "only.\n\n"
            f"--- DOCUMENT ---\n{document_text}"
        )

    if request_type == "insights":
        return (
            "Extract the key insights from the following document as a "
            "bulleted list (use '- ' for each bullet). Focus on the most "
            "important facts, findings, decisions, or action items. Aim "
            "for 5-10 bullets.\n\n"
            f"--- DOCUMENT ---\n{document_text}"
        )

    if request_type == "simplify":
        return (
            "Rewrite the following document in simpler, plain language "
            "that a general audience (no specialized background) could "
            "easily understand. Preserve all important meaning, just "
            "reduce jargon and complexity.\n\n"
            f"--- DOCUMENT ---\n{document_text}"
        )

    if request_type == "translate":
        language = target_language or "Spanish"
        return (
            f"Translate the following document into {language}. Preserve "
            "the original meaning, tone, and structure as closely as "
            "possible. Return only the translation, with no additional "
            "commentary.\n\n"
            f"--- DOCUMENT ---\n{document_text}"
        )

    if request_type == "analyze":
        return (
            "Perform a smart analysis of the following document. Identify: "
            "(1) the document's overall purpose and type, (2) its main "
            "themes or topics, (3) the tone, and (4) any notable strengths "
            "or gaps. Structure your answer with short headers for each "
            "part.\n\n"
            f"--- DOCUMENT ---\n{document_text}"
        )

    raise ValueError(f"Unknown AI request type: {request_type}")
