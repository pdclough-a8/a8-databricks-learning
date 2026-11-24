"""A8 Events seats-left app (Module 11). Streamlit on Databricks Apps; read-only.

The app queries as its own service principal, so that principal needs access to the view. The person using the app
is shown from the header Databricks Apps adds; this app does not act on their behalf.
"""
import os

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient

st.set_page_config(page_title="A8 Events: seats left", layout="wide")


@st.cache_resource
def client():
    return WorkspaceClient()  # picks up the app's service principal credentials from the environment


@st.cache_data(ttl=60)
def seats_left() -> pd.DataFrame:
    result = client().statement_execution.execute_statement(
        warehouse_id=os.environ["A8_WAREHOUSE_ID"], wait_timeout="30s",
        statement=f"SELECT event_name, city, event_date, capacity, booked, available "
                  f"FROM {os.environ['A8_VIEW']} WHERE status = 'scheduled' ORDER BY available")
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"Query {result.status.state.value}: {result.status.error}")
    columns = [c.name for c in result.manifest.schema.columns]
    frame = pd.DataFrame(result.result.data_array or [], columns=columns)
    for column in ("capacity", "booked", "available"):
        frame[column] = pd.to_numeric(frame[column])
    return frame


st.title("A8 Events: seats left")
st.caption("Synthetic data. Read-only.")
try:
    data = seats_left()
except Exception as error:  # show the reason on the page; the app log has the rest
    st.error(f"Could not read seats left: {error}")
    st.stop()

cities = st.multiselect("City", sorted(data["city"].unique()))
shown = data[data["city"].isin(cities)] if cities else data
low = int(st.number_input("Flag events with fewer seats left than", min_value=0, value=30, step=5))
left, right = st.columns(2)
left.metric("Scheduled events shown", len(shown))
right.metric("Events below the threshold", int((shown["available"] < low).sum()))
st.bar_chart(shown.set_index("event_name")["available"])
st.dataframe(shown, hide_index=True, use_container_width=True)

with st.expander("Who is running this, and who is looking at it?"):
    st.write("**The app runs as:**", client().current_user.me().user_name)
    st.write("**The page is being viewed by:**", st.context.headers.get("X-Forwarded-Email", "unknown"))
