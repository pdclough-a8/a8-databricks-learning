"""A8 pilot app. Simulation never constructs a Databricks client."""

import os
from pathlib import Path

import streamlit as st

from logic import answer_live, load_events, simulate_answer, with_availability

APP_TITLE = "A8 | Event Operations Assistant"
st.set_page_config(page_title=APP_TITLE, layout="centered")
st.caption("A8 LEARNING / DATA TO WORKING AI / PILOT")
st.title(APP_TITLE)
st.write("Find event availability. Check the evidence before making a decision.")
st.info("Learning fixture: six synthetic records, not live bookings. This app does not query your catalog table.")
rows = load_events()
with st.expander("See the evidence"):
    st.dataframe(with_availability(rows), hide_index=True)
live = st.checkbox("Use a live model (billable)", value=False)
st.caption("Simulation is the default. Live requests use the app service principal, not the visiting user.")
with st.form("ask"):
    question = st.text_input("Your question", value="Which events are in Leeds?", max_chars=1000)
    submitted = st.form_submit_button("Ask once" if live else "Run simulation")
if submitted:
    try:
        if live:
            endpoint = os.environ.get("SERVING_ENDPOINT", "")
            if not endpoint:
                raise ValueError("Model resource missing.")
            # Native workload authentication in Databricks Apps. Never paste a token here.
            from databricks.sdk import WorkspaceClient

            client = WorkspaceClient().serving_endpoints.get_open_ai_client().with_options(
                max_retries=0, timeout=45.0,
            )
            answer = answer_live(client, endpoint, question, rows)
        else:
            answer = simulate_answer(question, rows)
        # Plain text: model output is not trusted HTML or a clickable instruction.
        st.text(answer)
    except Exception:
        st.error(
            "No answer was produced. Check the question, model resource, endpoint access and "
            "app logs with your instructor. No automatic retry was made. "
            "Do not paste credentials or raw request logs into a tutor."
        )
st.caption("Check IDs, arithmetic and missing evidence. This pilot cannot make or cancel bookings.")
style = Path(__file__).parent / "style.css"
st.html(f"<style>{style.read_text(encoding='utf-8')}</style>")
