"""Learning modules: 13 lessons with video tutorials and quizzes. They are also the chatbot's knowledge base."""
import streamlit as st

from app_pages.common import db_session, visitor_id
from wealthwise import services
from wealthwise.rag.knowledge import load_modules

vid = visitor_id()
modules = {m["id"]: m for m in load_modules()}
with db_session() as db:
    scores = services.quiz_scores(db, vid)


def open_lesson(module_id: str | None) -> None:
    if module_id:
        st.query_params["lesson"] = module_id
    else:
        st.query_params.pop("lesson", None)


lesson = modules.get(st.query_params.get("lesson", ""))

# ---------- lesson list ----------
if not lesson:
    done = sum(1 for m in modules if scores.get(m, 0) >= 0.5)
    st.title("Lessons")
    st.caption("Short lessons with video tutorials and quizzes. The AI assistant answers from these same lessons.")
    st.progress(done / len(modules), text=f"{done} of {len(modules)} lessons completed (quiz score 50%+)")
    for row_start in range(0, len(modules), 3):
        for col, m in zip(st.columns(3), list(modules.values())[row_start:row_start + 3]):
            with col.container(border=True, height="stretch"):
                score = scores.get(m["id"])
                st.markdown(f"**{m['title']}**")
                st.caption(f"{m['level']} · {m['minutes']} min · {len(m['videos'])} video{'s' * (len(m['videos']) != 1)}"
                           + (f" · quiz {score:.0%}" if score is not None else ""))
                st.write(m["summary"])
                st.button("Open lesson", key=f"open_{m['id']}", on_click=open_lesson, args=(m["id"],))
    st.stop()

# ---------- one lesson ----------
st.button("← All lessons", on_click=open_lesson, args=(None,))
st.title(lesson["title"])
st.caption(f"{lesson['level']} · {lesson['minutes']} min read")

if lesson["videos"]:
    for col, v in zip(st.columns(len(lesson["videos"])), lesson["videos"]):
        col.video(f"https://www.youtube.com/watch?v={v['id']}")
        col.caption(f"**{v['channel']}** · {v['title']}")

st.markdown(lesson["markdown"].split("\n", 1)[1])  # the title is shown above
if lesson["sources"]:
    st.caption("Sources: " + " · ".join(f"[{s['title']}]({s['url']})" for s in lesson["sources"]))

st.divider()
st.subheader("Quick quiz")
with st.form(f"quiz_{lesson['id']}"):
    picks = [st.radio(f"{i}. {q['q']}", q["options"], index=None, key=f"{lesson['id']}_q{i}")
             for i, q in enumerate(lesson["quiz"], 1)]
    checked = st.form_submit_button("Check answers", type="primary")

if checked:
    if None in picks:
        st.warning("Answer every question first.")
    else:
        right = 0
        for q, pick in zip(lesson["quiz"], picks):
            correct = q["options"][q["answer"]]
            if pick == correct:
                right += 1
                st.success(f"**{q['q']}** ✓ {correct}  \n💡 {q['why']}")
            else:
                st.error(f"**{q['q']}** ✗ You picked “{pick}”; the answer is “{correct}”.  \n💡 {q['why']}")
        with db_session() as db:
            services.save_quiz_score(db, vid, lesson["id"], right / len(lesson["quiz"]))
        st.markdown(f"### You got {right} of {len(lesson['quiz'])}")
