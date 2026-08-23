# FinGraph Dashboard — Graph Visualization

## Approach
Using Neo4j Browser's built-in graph visualization instead of Neo4j Bloom. Bloom requires Neo4j Enterprise Edition or Neo4j Desktop with a separate Bloom install — this project runs on Neo4j Community Edition via Docker, where Bloom isn't available. Neo4j Browser's native graph view (available with any edition) covers the same core need: rendering the account network as an interactive node-link graph.

## How to view the graph
```cypher
MATCH (a:Account)-[r:TRANSFERRED_TO]->(b:Account)
RETURN a, r, b
LIMIT 300
```
Run in Neo4j Browser (`http://localhost:7474`), then click the graph icon on the results panel (instead of the table view) to render it as a network.

## Styling suspicious nodes
Clicking on a node in the graph view opens a style panel (color, size) that can be applied per node label. Used to visually highlight the two planted shell accounts as larger/differently colored nodes so the "Starburst" pattern is visible at a glance.

## Verified results (GDS algorithms, run on 521 accounts / 600 relationships)
- **PageRank** correctly scored both planted shell accounts (`ACCB878C18A`: 8.75, `ACCA03AC233`: 7.09) more than 4x higher than the next-highest legitimate account (1.97) — with zero manual tagging.
- **WCC (Weakly Connected Components)** correctly separated two independent transaction networks (created by two separate simulator runs) into distinct clusters of 237 and 236 accounts, each centered on its own shell account.
- **Louvain** ran successfully on the same projected graph.

## Why this scope decision is reasonable
A custom React + neovis.js dashboard, or Neo4j Enterprise/Bloom, remain possible v2 enhancements if time allows. For this build, Neo4j Browser's native visualization plus the verified GDS results above already demonstrate the core detection capability without added infrastructure complexity.

## Status
- [x] Graph visualization confirmed working in Neo4j Browser
- [x] GDS algorithms (PageRank, WCC, Louvain) run and verified against planted fraud patterns
- [x] "Freeze account" action — built as both a CLI (`freeze_account.py`) and a dashboard button (`app.py`)
- [x] Account risk scoring — combines starburst, just-under-threshold, high-volume outbound, and circular-flow signals into one explainable score (`detection_queries.cypher`, query 7), surfaced on the dashboard
- [ ] Manual node styling applied and screenshotted for the final report
- [ ] Automation/alerts layer (Slack webhook) — not yet built
