import os
from src.core.ports import LLMPort

class RuleLLMAdapter(LLMPort):
    def route(self, query: str, has_coords: bool) -> str:
        q = query.lower()
        if has_coords and ("notam" in q or "crane" in q or "dgca" in q): return "both"
        if has_coords: return "act"
        return "retrieve"
    def respond(self, verdict: str, reason: str, citations: list) -> str:
        if verdict == "BLOCK": return f"{verdict}: {reason} — reduce to 80m. Citations: {', '.join(citations)}"
        return f"{verdict}: clear — citations {', '.join(citations)}"

class GroqLLMAdapter(LLMPort):
    def __init__(self):
        try:
            from langchain_groq import ChatGroq
            self.llm = ChatGroq(model=os.getenv("GROQ_MODEL","llama-3.1-8b-instant"), api_key=os.getenv("GROQ_API_KEY"), temperature=0)
            self.ok = True
        except Exception as e: print(f"Groq not ready {e}"); self.ok=False; self.fallback=RuleLLMAdapter()
    def route(self, query: str, has_coords: bool) -> str:
        if not self.ok: return self.fallback.route(query, has_coords)
        try:
            prompt = f"Decide retrieve/act/both for query '{query}' has_coords={has_coords}. Reply one word."
            r = self.llm.invoke(prompt).content.strip().lower()
            if "both" in r: return "both"
            if "act" in r: return "act"
            return "retrieve"
        except: return self.fallback.route(query, has_coords)
    def respond(self, verdict: str, reason: str, citations: list) -> str:
        if not self.ok: return self.fallback.respond(verdict, reason, citations)
        try:
            prompt = f"Synthesize {verdict}: {reason} Citations {citations} — one sentence."
            return self.llm.invoke(prompt).content.strip()
        except: return self.fallback.respond(verdict, reason, citations)

# Local Ollama optional — valid but needs 6GB VRAM, slower than Groq, keep as fallback
class OllamaLLMAdapter(LLMPort):
    def __init__(self, model="llama3.1:8b"):
        try:
            from langchain_ollama import ChatOllama
            self.llm = ChatOllama(model=model, temperature=0)
            self.ok=True
        except: self.ok=False; self.fallback=RuleLLMAdapter()
    def route(self, query, has_coords): return self.fallback.route(query, has_coords) if not self.ok else GroqLLMAdapter.route(self, query, has_coords)
    def respond(self, verdict, reason, citations): return self.fallback.respond(verdict, reason, citations) if not self.ok else GroqLLMAdapter.respond(self, verdict, reason, citations)
