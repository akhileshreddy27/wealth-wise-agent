from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.assistant import chat
from app.db import get_db
from app.rag.knowledge import load_modules

router = APIRouter(prefix="/api", tags=["learn"])
LIST_FIELDS = ("id", "title", "level", "minutes", "summary")


@router.get("/learn/modules")
def modules():
    return [{k: m[k] for k in LIST_FIELDS} for m in load_modules()]


@router.get("/learn/modules/{module_id}")
def module(module_id: str):
    for m in load_modules():
        if m["id"] == module_id:
            return {k: m[k] for k in (*LIST_FIELDS, "markdown", "videos", "video_query", "sources", "quiz")}
    raise HTTPException(404, "Lesson not found")


class Message(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=30)


@router.post("/chat")
def chat_endpoint(body: ChatIn, db: Session = Depends(get_db)):
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user.")
    try:
        return chat(db, [m.model_dump() for m in body.messages])
    except Exception as e:  # quota / network errors from Gemini
        raise HTTPException(502, f"The AI service failed: {e}")
