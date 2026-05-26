import os
from dotenv import load_dotenv

load_dotenv()

# We support "openai" and "google"
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()


def get_active_provider() -> str:
    """Detects the available provider based on API keys and configuration."""
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if DEFAULT_PROVIDER == "openai" and openai_key:
        return "openai"
    elif DEFAULT_PROVIDER == "google" and google_key:
        return "google"

    # Auto-detection fallback if LLM_PROVIDER is not set or not matching
    if google_key:
        return "google"
    if openai_key:
        return "openai"

    raise ValueError(
        "Missing LLM API credentials! Please set either OPENAI_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY "
        "in your environment or .env file."
    )


def get_llm(temperature: float = 0.2, model_name: str = None):
    """
    Returns the appropriate LangChain chat model.
    By default:
      - OpenAI uses 'gpt-4o'
      - Google Gemini uses 'gemini-3.1-flash-lite'
    """
    provider = get_active_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = model_name or "gpt-4o"
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = model_name or "gemini-3.1-flash-lite"
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def get_embeddings():
    """
    Returns the appropriate LangChain embeddings class.
    By default:
      - OpenAI uses 'text-embedding-3-small'
      - Google Gemini uses 'models/text-embedding-004'
    """
    provider = get_active_provider()

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY")
        )
    elif provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
