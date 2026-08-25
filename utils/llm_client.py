import langchain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from database.config import settings

# Enable global LangChain debug tracing to print prompts and responses to the terminal console
langchain.debug = True

class LoggingChatModelWrapper:
    def __init__(self, model):
        self.model = model

    async def ainvoke(self, input, config=None, **kwargs):
        prompt_text = ""
        if isinstance(input, list):
            prompt_text = "\n".join([str(m.content) if hasattr(m, 'content') else str(m) for m in input])
        else:
            prompt_text = str(input)
            
        print("\n" + "="*30 + " [LLM REQUEST START] " + "="*30)
        print(f"Model: {getattr(self.model, 'model_name', getattr(self.model, 'model', 'Unknown'))}")
        print(f"Prompt:\n{prompt_text.strip()}")
        print("="*80)
        
        response = await self.model.ainvoke(input, config=config, **kwargs)
        
        print("\n" + "="*30 + " [LLM RESPONSE START] " + "="*30)
        print(f"Response:\n{response.content.strip()}")
        print("="*80 + "\n")
        
        return response

def get_llm():
    """
    Returns the configured LLM client (Mistral or Gemini) based on settings.
    """
    if settings.MODE == "Cloud":
        if settings.GEMINI_API_KEY:
            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.2
            )
        elif settings.MISTRAL_API_KEY:
            # Using ChatOpenAI as a generic client for Mistral Cloud since Mistral's API is OpenAI compatible
            llm = ChatOpenAI(
                model=settings.MODEL_NAME,
                api_key=settings.MISTRAL_API_KEY,
                base_url="https://api.mistral.ai/v1",
                temperature=0.2
            )
        else:
            raise ValueError("No valid LLM configuration found in .env (Check MODE, API_KEYs)")
    else:
        # Local Mode
        base_url = settings.MISTRAL_LOCAL_URL
        if base_url and not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
            base_url = base_url.rstrip("/") + "/v1"
        llm = ChatOpenAI(
            model=settings.MISTRAL_LOCAL_MODEL,
            api_key="local",
            base_url=base_url,
            temperature=0.2
        )
    return LoggingChatModelWrapper(llm)

