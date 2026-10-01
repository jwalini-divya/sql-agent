"""Tests with a fake LLM: no API key, no internet, run in under a second."""
import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from agent import build_graph, clean_sql
from app import app, get_llm
from db import create_sample_db, run_query


def fake_llm(sql_replies: list[str], prompts: list[str] | None = None):
    """Pretend to be Gemini: return the next SQL for SQL prompts, a fixed sentence for answer prompts."""
    replies = iter(sql_replies)

    def reply(prompt_value):
        text = prompt_value.to_string()
        if prompts is not None:
            prompts.append(text)
        if "You write one SQLite SELECT query" in text:
            return next(replies)
        return "Fake answer."

    return RunnableLambda(reply)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shop.db"
    create_sample_db(path)
    return path


def test_answers_from_the_database(db):
    llm = fake_llm(["SELECT name FROM customers WHERE city = 'Hyderabad' ORDER BY name"])

    result = build_graph(llm, db).invoke({"question": "Which customers are in Hyderabad?"})

    assert result["rows"] == [{"name": "Asha"}, {"name": "Kiran"}]
    assert result["attempts"] == 1
    assert result["answer"] == "Fake answer."


def test_fixes_its_own_sql_error(db):
    prompts = []
    llm = fake_llm(["SELECT nme FROM customers", "SELECT name FROM customers WHERE id = 1"], prompts)

    result = build_graph(llm, db).invoke({"question": "Who is customer 1?"})

    assert result["attempts"] == 2
    assert result["rows"] == [{"name": "Asha"}]
    assert "no such column: nme" in prompts[1]          # the second try was shown the error


def test_gives_up_after_two_failed_tries(db):
    llm = fake_llm(["SELECT nme FROM customers", "SELECT nme FROM customers"])

    result = build_graph(llm, db).invoke({"question": "Who is customer 1?"})

    assert result["attempts"] == 2
    assert result["answer"].startswith("Sorry, I couldn't get this from the database.")


def test_only_select_queries_can_run(db):
    with pytest.raises(ValueError):
        run_query("DELETE FROM orders", db)
    with pytest.raises(Exception):                      # read-only connection blocks a hidden write
        run_query("WITH x AS (SELECT 1) DELETE FROM orders", db)
    assert run_query("SELECT COUNT(*) AS n FROM orders", db) == [{"n": 10}]


def test_removes_markdown_fences():
    assert clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"


def test_api_returns_answer_and_sql():
    app.dependency_overrides[get_llm] = lambda: fake_llm(["SELECT COUNT(*) AS n FROM products"])
    client = TestClient(app)

    r = client.post("/ask", json={"question": "How many products are there?"})

    assert r.status_code == 200
    assert r.json() == {"answer": "Fake answer.", "sql": "SELECT COUNT(*) AS n FROM products",
                        "rows": [{"n": 5}], "attempts": 1}
    assert client.post("/ask", json={"question": ""}).status_code == 422    # Pydantic validation
    app.dependency_overrides.clear()
