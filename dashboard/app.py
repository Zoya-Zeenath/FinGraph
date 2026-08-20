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
import plotly.express as px

from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "fingraph123"

st.set_page_config(page_title="FinGraph Fraud Detection", page_icon="🕸️", layout="wide")

# Light visual polish — tighter spacing, card-style metrics, muted dividers
# Colors are set explicitly (not relying on theme defaults) so cards stay
# readable whether Streamlit is running in light or dark mode.
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #f7f8fa;
        border: 1px solid #e3e6ea;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        color: #64748b;
    }
    div[data-testid="stMetricValue"] {
        color: #111827;
        font-weight: 700;
    }
    hr { margin: 1.2rem 0; opacity: 0.15; }
    </style>
    """,
    unsafe_allow_html=True,
)


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

# ---- Summary metrics ----
starburst = get_starburst_accounts()
all_transactions = get_transaction_volume()
frozen_count = len(get_frozen_accounts())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Transactions", f"{len(all_transactions):,}")
m2.metric("Total Volume", f"${sum(t['amount'] for t in all_transactions):,.0f}" if all_transactions else "$0")
m3.metric("Flagged Accounts", len(starburst))
m4.metric("Frozen Accounts", frozen_count)

st.divider()

col1, col2 = st.columns(2)

# ---- Starburst Fraud panel ----
with col1:
    st.subheader(" Starburst Fraud")
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

# ---- Transaction Amount Analysis ----
st.subheader(" Transaction Amount Analysis")
transactions = all_transactions  # already fetched above for the metrics row

if transactions:
    df = pd.DataFrame(transactions)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    chart_col1, chart_col2 = st.columns(2)

    # Distribution — where do amounts cluster? The smurfing band ($9.5k-$9.9k)
    # is called out in its own bucket and colored separately so it stands out.
    with chart_col1:
        st.markdown("**Amount distribution**")
        bin_edges = [0, 500, 1000, 1500, 2000, 2500, 3000, 9500, 9900, 10000]
        bin_labels = [
            "$0-500", "$500-1k", "$1k-1.5k", "$1.5k-2k",
            "$2k-2.5k", "$2.5k-3k", "$3k-9.5k",
            "$9.5k-9.9k (smurf zone)", "$9.9k-10k",
        ]
        df["bucket"] = pd.cut(df["amount"], bins=bin_edges, labels=bin_labels, include_lowest=True)
        counts = df["bucket"].value_counts().reindex(bin_labels).fillna(0).astype(int)

        fig = px.bar(
            x=counts.index,
            y=counts.values,
            labels={"x": "Amount range", "y": "Transactions"},
            color=[("Smurf zone" if "smurf" in b else "Normal") for b in counts.index],
            color_discrete_map={"Smurf zone": "#e74c3c", "Normal": "#3b82f6"},
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-30, margin=dict(t=10, b=10), height=340)
        st.plotly_chart(fig, use_container_width=True)

    # Trend over time — transactions resampled per minute instead of one bar
    # per row, so the shape of the traffic (and the smurfing spike) is readable.
    with chart_col2:
        st.markdown("**Volume over time**")
        ts = (
            df.set_index("timestamp")
            .resample("1min")
            .agg(total_amount=("amount", "sum"))
        )
        fig2 = px.area(
            ts,
            y="total_amount",
            labels={"total_amount": "Total $ / minute", "timestamp": "Time"},
        )
        fig2.update_traces(line_color="#3b82f6", fillcolor="rgba(59,130,246,0.25)")
        fig2.update_layout(margin=dict(t=10, b=10), height=340)
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No transaction data yet.")
