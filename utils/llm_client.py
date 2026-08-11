from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from config import settings

def get_llm():
    """
    Returns the configured LLM client (Mistral or Gemini) based on settings.
    """
    if settings.MODE == "Cloud":
        if settings.GEMINI_API_KEY:
            return ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.2
            )
        elif settings.MISTRAL_API_KEY:
            # Using ChatOpenAI as a generic client for Mistral Cloud since Mistral's API is OpenAI compatible
            return ChatOpenAI(
                model=settings.MODEL_NAME,
                api_key=settings.MISTRAL_API_KEY,
                base_url="https://api.mistral.ai/v1",
                temperature=0.2
            )
    else:
        # Local Mode
        return ChatOpenAI(
            model=settings.MISTRAL_LOCAL_MODEL,
            api_key="local",
            base_url=settings.MISTRAL_LOCAL_URL,
            temperature=0.2
        )
    
    # Fallback to a default if nothing is configured
    raise ValueError("No valid LLM configuration found in .env (Check MODE, API_KEYs)")
