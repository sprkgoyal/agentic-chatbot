import os
from dotenv import load_dotenv

load_dotenv()

# We support "openai" and "google"
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL_NAME", None)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)
DEFAULT_GOOGLE_MODEL = os.getenv("GOOGLE_MODEL_NAME", "").lower()


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


def get_llm(temperature: float = 0.2):
    """
    Returns the appropriate LangChain chat model.
    By default:
      - OpenAI uses 'gpt-4o'
      - Google Gemini uses 'gemini-3.1-flash-lite'
    """
    provider = get_active_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = DEFAULT_OPENAI_MODEL or "gpt-4o"
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=OPENAI_BASE_URL
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = DEFAULT_GOOGLE_MODEL or "gemini-3.1-flash-lite"
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


import logging
logger = logging.getLogger("aegis_backend.llm_factory")

class SafeEmbeddings:
    def __init__(self, actual_embeddings, dim: int = 768):
        self.actual_embeddings = actual_embeddings
        self.dim = dim
        
    def embed_query(self, text: str) -> list:
        try:
            return self.actual_embeddings.embed_query(text)
        except Exception as e:
            logger.warning(f"Embedding query failed ({e}). Returning dummy {self.dim}-dim vector.")
            return [0.0] * self.dim
            
    def embed_documents(self, texts: list) -> list:
        try:
            return self.actual_embeddings.embed_documents(texts)
        except Exception as e:
            logger.warning(f"Embedding documents failed ({e}). Returning dummy {self.dim}-dim vectors.")
            return [[0.0] * self.dim for _ in texts]

def get_embeddings():
    """
    Returns the appropriate LangChain embeddings class.
    By default:
      - OpenAI uses 'text-embedding-3-small' (dim 1536)
      - Google Gemini uses 'models/text-embedding-004' (dim 768)
    """
    provider = get_active_provider()

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        actual = OpenAIEmbeddings(
            model="BAAI/bge-m3",
            base_url="http://107.99.236.181:5678/v1"
        )
        return SafeEmbeddings(actual, dim=1536)
    elif provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        actual = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004"
        )
        return SafeEmbeddings(actual, dim=768)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
