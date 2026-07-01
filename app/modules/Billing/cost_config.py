CUSTO_POR_PROVIDER: dict[str, tuple[float, float]] = {
    # Gemini 2.5 Flash: $0.30/1M input, $2.50/1M output
    "gemini": (0.000_000_30, 0.000_002_50),
    # Bedrock Claude Sonnet 4: $3.00/1M input, $15.00/1M output
    "bedrock": (0.000_003_0, 0.000_015_0),
    # Ollama: self-hosted, custo zero
    "ollama": (0.000_000_0, 0.000_000_0),
    # Aria: fallback ate ter pricing real
    "aria": (0.000_003_0, 0.000_015_0),
}

DEFAULT_CUSTO: tuple[float, float] = (0.000_003_0, 0.000_015_0)
