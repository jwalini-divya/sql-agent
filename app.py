"""FastAPI app: ask questions about the shop database in plain English."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from agent import build_graph
from db import create_sample_db

load_dotenv()          # reads GOOGLE_API_KEY from the .env file
create_sample_db()

app = FastAPI(title="SQL Agent", description="Ask questions about a sample shop database in plain English.")


@lru_cache
def get_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["Which customer spent the most money?"])


class AskResponse(BaseModel):
    answer: str
    sql: str
    rows: list[dict]
    attempts: int


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/docs")


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, llm=Depends(get_llm)):
    result = build_graph(llm).invoke({"question": req.question})
    return AskResponse(answer=result["answer"], sql=result["sql"], rows=result["rows"], attempts=result["attempts"])
