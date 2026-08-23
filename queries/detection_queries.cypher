// ============================================================
// FinGraph — Fraud Detection Queries
// Run these one at a time in Neo4j Browser (http://localhost:7474)
// ============================================================


// ------------------------------------------------------------
// 1. STARBURST DETECTION
// Finds accounts receiving from many distinct senders — the
// classic "smurfing into one shell account" pattern.
// ------------------------------------------------------------
MATCH (sender:Account)-[t:TRANSFERRED_TO]->(hub:Account)
WITH hub, count(DISTINCT sender) AS numSenders, sum(t.amount) AS totalIn
WHERE numSenders > 10
RETURN hub.account_id AS shellAccount, numSenders, totalIn
ORDER BY numSenders DESC;


// ------------------------------------------------------------
// 2. "JUST UNDER THE THRESHOLD" DETECTION
// Finds individual transactions suspiciously close to (but
// under) the $10,000 reporting threshold — the smurfing signature.
// ------------------------------------------------------------
MATCH (sender:Account)-[t:TRANSFERRED_TO]->(receiver:Account)
WHERE t.amount >= 9000 AND t.amount < 10000
RETURN sender.account_id AS sender, receiver.account_id AS receiver,
       t.amount AS amount, t.timestamp AS timestamp
ORDER BY t.amount DESC;


// ------------------------------------------------------------
// 3. COMBINED SIGNAL — accounts that BOTH send just-under-threshold
// amounts AND funnel into a shared hub. This is a stronger signal
// than either check alone.
// ------------------------------------------------------------
MATCH (sender:Account)-[t:TRANSFERRED_TO]->(hub:Account)
WHERE t.amount >= 9000 AND t.amount < 10000
WITH hub, count(DISTINCT sender) AS numSuspiciousSenders, sum(t.amount) AS totalIn
WHERE numSuspiciousSenders > 5
RETURN hub.account_id AS shellAccount, numSuspiciousSenders, totalIn
ORDER BY numSuspiciousSenders DESC;


// ------------------------------------------------------------
// 4. CIRCULAR FLOW DETECTION (A -> B -> C -> A)
// A classic money-laundering pattern: funds cycle back to the
// original sender through intermediary accounts.
// ------------------------------------------------------------
MATCH path = (a:Account)-[:TRANSFERRED_TO]->(b:Account)-[:TRANSFERRED_TO]->(c:Account)-[:TRANSFERRED_TO]->(a)
WHERE a <> b AND b <> c AND a <> c
RETURN a.account_id AS accountA, b.account_id AS accountB, c.account_id AS accountC
LIMIT 25;


// ------------------------------------------------------------
// 5. HIGH-VOLUME OUTBOUND ACCOUNTS
// Accounts whose total outbound transfers are unusually high —
// useful as a general triage list even without a specific pattern.
// ------------------------------------------------------------
MATCH (sender:Account)-[t:TRANSFERRED_TO]->()
WITH sender, sum(t.amount) AS totalOut, count(t) AS numTransactions
WHERE totalOut > 50000
RETURN sender.account_id AS account, totalOut, numTransactions
ORDER BY totalOut DESC;


// ------------------------------------------------------------
// 6. INSPECT A SPECIFIC ACCOUNT'S FULL NEIGHBORHOOD
// Replace 'ACCOUNT_ID_HERE' with an account_id from query 1 or 3
// to visually inspect everything connected to a flagged account.
// ------------------------------------------------------------
MATCH (a:Account {account_id: "ACCOUNT_ID_HERE"})-[r]-(neighbor)
RETURN a, r, neighbor;

// ------------------------------------------------------------
// 7. ACCOUNT RISK SCORING
// Combines multiple fraud signals into one explainable score.
// Higher score = higher investigation priority.
//
// Score weights (out of 100), each mirroring the thresholds
// already used in queries 1, 3, and 5 above:
//   Starburst hub (>10 distinct senders)          : +40
//   Just-under-threshold inbound (>5 txns)        : +30
//   High-volume outbound (>$50,000 total)         : +20
//   Involved in a circular flow (A->B->C->A)      : +10
// ------------------------------------------------------------
MATCH (a:Account)

// Signals 1 & 2: inbound transfers into this account
OPTIONAL MATCH (sender:Account)-[inTxn:TRANSFERRED_TO]->(a)
WITH a,
     count(DISTINCT sender) AS numSenders,
     sum(CASE WHEN inTxn.amount >= 9000 AND inTxn.amount < 10000 THEN 1 ELSE 0 END) AS suspiciousInboundCount

// Signal 3: outbound transfers from this account
OPTIONAL MATCH (a)-[outTxn:TRANSFERRED_TO]->()
WITH a, numSenders, suspiciousInboundCount, sum(outTxn.amount) AS totalOut

// Signal 4: is this account part of a 3-hop circular flow?
OPTIONAL MATCH (a)-[:TRANSFERRED_TO]->(b:Account)-[:TRANSFERRED_TO]->(c:Account)-[:TRANSFERRED_TO]->(a)
WHERE a <> b AND b <> c AND a <> c
WITH a, numSenders, suspiciousInboundCount, totalOut, (count(b) > 0) AS inCircularFlow

WITH a, numSenders, suspiciousInboundCount, coalesce(totalOut, 0) AS totalOut, inCircularFlow,
     (CASE WHEN numSenders > 10 THEN 40 ELSE 0 END) +
     (CASE WHEN suspiciousInboundCount > 5 THEN 30 ELSE 0 END) +
     (CASE WHEN totalOut > 50000 THEN 20 ELSE 0 END) +
     (CASE WHEN inCircularFlow THEN 10 ELSE 0 END) AS riskScore

WHERE riskScore > 0
RETURN a.account_id AS account, riskScore, numSenders, suspiciousInboundCount,
       totalOut, inCircularFlow
ORDER BY riskScore DESC;