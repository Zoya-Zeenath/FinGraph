"""
FinGraph — Streamlit Dashboard
A browser-based dashboard showing fraud detection results, live alerts,
and a freeze-account action — all in one screen instead of raw Cypher queries.

Run with:
    streamlit run dashboard/app.py

Then open the URL it prints (usually http://localhost:8501)
"""

import streamlit as st
import pandas as pd
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "fingraph123"

st.set_page_config(page_title="FinGraph Fraud Detection", page_icon="🕸️", layout="wide")


@st.cache_resource
def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run_query(query, params=None):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, params or {})
        return [dict(record) for record in result]


# ---------------------------------------------------------
# Data-fetching functions — each one wraps one of our existing
# Cypher detection queries so the dashboard just displays results.
# ---------------------------------------------------------

def get_starburst_accounts():
    query = """
    MATCH (sender:Account)-[t:TRANSFERRED_TO]->(hub:Account)
    WITH hub, count(DISTINCT sender) AS numSenders, sum(t.amount) AS totalIn
    WHERE numSenders > 10
    RETURN hub.account_id AS account, numSenders AS num_senders,
           totalIn AS total_in, coalesce(hub.frozen, false) AS frozen
    ORDER BY numSenders DESC
    """
    return run_query(query)


def get_circular_flows():
    query = """
    MATCH path = (a:Account)-[:TRANSFERRED_TO]->(b:Account)-[:TRANSFERRED_TO]->(c:Account)-[:TRANSFERRED_TO]->(a)
    WHERE a <> b AND b <> c AND a <> c
    RETURN a.account_id AS account_a, b.account_id AS account_b, c.account_id AS account_c
    LIMIT 25
    """
    return run_query(query)


def get_transaction_volume():
    query = """
    MATCH ()-[t:TRANSFERRED_TO]->()
    RETURN t.amount AS amount, t.timestamp AS timestamp
    ORDER BY t.timestamp
    """
    return run_query(query)


def get_frozen_accounts():
    query = """
    MATCH (a:Account {frozen: true})
    RETURN a.account_id AS account, a.frozen_at AS frozen_at, a.frozen_reason AS reason
    ORDER BY a.frozen_at DESC
    """
    return run_query(query)


def freeze_account(account_id):
    query = """
    MATCH (sender:Account)-[:TRANSFERRED_TO]->(hub:Account {account_id: $account_id})
    SET hub.frozen = true, hub.frozen_at = datetime(), hub.frozen_reason = 'Starburst hub account'
    WITH hub, collect(sender) AS senders
    UNWIND senders AS sender
    SET sender.frozen = true, sender.frozen_at = datetime(), sender.frozen_reason = 'Part of flagged syndicate'
    RETURN hub.account_id AS hub_account, count(sender) AS frozen_senders
    """
    return run_query(query, {"account_id": account_id})


# ---------------------------------------------------------
# Dashboard layout
# ---------------------------------------------------------

st.title(" FinGraph — Fraud Syndicate Analytics")
st.caption("Real-time fraud detection dashboard, backed by Neo4j + Cypher pattern matching")

if st.button(" Refresh Dashboard"):
    st.cache_resource.clear()
    st.rerun()

col1, col2 = st.columns(2)

# ---- Starburst Fraud panel ----
with col1:
    st.subheader(" Starburst Fraud")
    starburst = get_starburst_accounts()
    if starburst:
        df = pd.DataFrame(starburst)
        df["total_in"] = df["total_in"].round(2)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No Starburst patterns detected yet. Run the simulator + consumer first.")

# ---- Circular Fraud panel ----
with col2:
    st.subheader(" Circular Fraud")
    circular = get_circular_flows()
    if circular:
        st.dataframe(pd.DataFrame(circular), use_container_width=True, hide_index=True)
    else:
        st.info("No circular flow patterns (A→B→C→A) detected in current data.")

st.divider()

# ---- Alerts panel (this replaces the Slack notification) ----
st.subheader(" Active Alerts")
alert_accounts = [a for a in starburst if a["num_senders"] > 10 and not a["frozen"]]
if alert_accounts:
    for a in alert_accounts:
        st.warning(
            f"**{a['account']}** received transfers from **{a['num_senders']} distinct accounts** "
            f"totaling **${a['total_in']:,.2f}** — matches Starburst (smurfing) pattern."
        )
else:
    st.success("No active (unfrozen) alerts — all flagged accounts are frozen or no fraud detected.")

st.divider()

# ---- Freeze account action ----
st.subheader(" Freeze Account")
flagged_ids = [a["account"] for a in starburst if not a["frozen"]]
if flagged_ids:
    selected = st.selectbox("Select a flagged account to freeze", flagged_ids)
    if st.button(f"Freeze {selected} and its syndicate"):
        result = freeze_account(selected)
        if result:
            st.success(
                f"Froze {result[0]['hub_account']} and "
                f"{result[0]['frozen_senders']} connected accounts."
            )
            st.rerun()
else:
    st.info("No unfrozen flagged accounts to act on right now.")

st.divider()

# ---- Frozen accounts log ----
st.subheader(" Frozen Accounts")
frozen = get_frozen_accounts()
if frozen:
    st.dataframe(pd.DataFrame(frozen), use_container_width=True, hide_index=True)
else:
    st.info("No accounts frozen yet.")

st.divider()

# ---- Transaction volume chart ----
st.subheader(" Transaction Amount Analysis")
transactions = get_transaction_volume()
if transactions:
    df = pd.DataFrame(transactions)
    st.bar_chart(df["amount"])
else:
    st.info("No transaction data yet.")
