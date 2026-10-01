"""The agent: English question -> SQL -> run it -> plain-English answer.

LangGraph steps:
    START -> write_sql -> run_sql
    run_sql --(worked)------------------------> answer -> END
    run_sql --(error, one more try allowed)---> write_sql   (it fixes its own SQL)
    run_sql --(error, no tries left)----------> answer -> END
"""
import sqlite3
from pathlib import Path
from typing import TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from db import DB_PATH, get_schema, run_query

MAX_ATTEMPTS = 2


class State(TypedDict, total=False):
    question: str
    sql: str
    rows: list[dict]
    error: str
    attempts: int
    answer: str


SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You write one SQLite SELECT query that answers the question. Use only these tables:\n{schema}\n"
     "Return only the SQL, with no explanation and no markdown."),
    ("human", "Question: {question}{error_note}"),
])

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Answer the question in one or two simple sentences, using only the query result. "
     "If the result is empty, say that no matching data was found."),
    ("human", "Question: {question}\nSQL: {sql}\nResult: {rows}"),
])


def clean_sql(text: str) -> str:
    """LLMs sometimes wrap SQL in ```sql fences; remove them."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip()


def build_graph(llm, db_path: Path = DB_PATH):
    """llm is passed in, so tests can use a fake one."""
    sql_chain = SQL_PROMPT | llm | StrOutputParser()
    answer_chain = ANSWER_PROMPT | llm | StrOutputParser()
    schema = get_schema(db_path)

    def write_sql(state: State) -> State:
        error_note = ""
        if state.get("error"):   # second try: show the LLM its mistake
            error_note = (f"\n\nYour previous query:\n{state['sql']}\n"
                          f"failed with this error: {state['error']}\nWrite a corrected query.")
        sql = sql_chain.invoke({"schema": schema, "question": state["question"], "error_note": error_note})
        return {"sql": clean_sql(sql), "attempts": state.get("attempts", 0) + 1}

    def run_sql(state: State) -> State:
        try:
            return {"rows": run_query(state["sql"], db_path), "error": ""}
        except (sqlite3.Error, ValueError) as e:
            return {"rows": [], "error": str(e)}

    def answer(state: State) -> State:
        if state["error"]:
            return {"answer": f"Sorry, I couldn't get this from the database. Last error: {state['error']}"}
        text = answer_chain.invoke({"question": state["question"], "sql": state["sql"], "rows": state["rows"]})
        return {"answer": text.strip()}

    def after_run(state: State) -> str:
        if state["error"] and state["attempts"] < MAX_ATTEMPTS:
            return "write_sql"
        return "answer"

    graph = StateGraph(State)
    graph.add_node("write_sql", write_sql)
    graph.add_node("run_sql", run_sql)
    graph.add_node("answer", answer)
    graph.add_edge(START, "write_sql")
    graph.add_edge("write_sql", "run_sql")
    graph.add_conditional_edges("run_sql", after_run, ["write_sql", "answer"])
    graph.add_edge("answer", END)
    return graph.compile()
