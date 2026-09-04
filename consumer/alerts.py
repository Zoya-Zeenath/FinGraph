"""
FinGraph — Automation / Alerts Layer
Runs the account risk-scoring query on a loop and fires a Slack
message and/or email whenever an account crosses a risk threshold —
this is the "rules engine" piece from the Week 4 plan.

Usage:
    python alerts.py
"""

import os
import time
import smtplib
from email.mime.text import MIMEText

import requests
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "fingraph123")

# ---- Alert thresholds & timing ----
RISK_THRESHOLD = 50          # fire an alert once an account's score crosses this
CHECK_INTERVAL_SECONDS = 30  # how often to re-run the risk query

# ---- Slack ----
# Never hardcode this — GitHub's push protection will (rightly) block
# the commit. Set it before running:
#   PowerShell:  $env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
#   bash/zsh:    export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_ENABLED = bool(SLACK_WEBHOOK_URL)

# ---- Email ----
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # use a Gmail "App Password", not your real one
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_ENABLED = bool(SMTP_USER and SMTP_PASSWORD and EMAIL_TO)

RISK_SCORE_QUERY = """
MATCH (a:Account)
OPTIONAL MATCH (sender:Account)-[inTxn:TRANSFERRED_TO]->(a)
WITH a,
     count(DISTINCT sender) AS numSenders,
     sum(CASE WHEN inTxn.amount >= 9000 AND inTxn.amount < 10000 THEN 1 ELSE 0 END) AS suspiciousInboundCount
OPTIONAL MATCH (a)-[outTxn:TRANSFERRED_TO]->()
WITH a, numSenders, suspiciousInboundCount, sum(outTxn.amount) AS totalOut
OPTIONAL MATCH (a)-[:TRANSFERRED_TO]->(b:Account)-[:TRANSFERRED_TO]->(c:Account)-[:TRANSFERRED_TO]->(a)
WHERE a <> b AND b <> c AND a <> c
WITH a, numSenders, suspiciousInboundCount, totalOut, (count(b) > 0) AS inCircularFlow
WITH a, numSenders, suspiciousInboundCount, coalesce(totalOut, 0) AS totalOut, inCircularFlow,
     (CASE WHEN numSenders > 10 THEN 40 ELSE 0 END) +
     (CASE WHEN suspiciousInboundCount > 5 THEN 30 ELSE 0 END) +
     (CASE WHEN totalOut > 50000 THEN 20 ELSE 0 END) +
     (CASE WHEN inCircularFlow THEN 10 ELSE 0 END) AS riskScore
WHERE riskScore >= $threshold
RETURN a.account_id AS account, riskScore, numSenders, suspiciousInboundCount, totalOut, inCircularFlow
ORDER BY riskScore DESC
"""

# Tracks accounts we've already alerted on, so a restart-free run
# doesn't spam the same alert every 30 seconds.
already_alerted = set()


def get_high_risk_accounts(driver, threshold):
    with driver.session() as session:
        result = session.run(RISK_SCORE_QUERY, threshold=threshold)
        return [dict(r) for r in result]


def format_message(account):
    return (
        f"*FinGraph Alert — High Risk Account*\n"
        f"Account: `{account['account']}`\n"
        f"Risk Score: *{account['riskScore']}/100*\n"
        f"Distinct senders: {account['numSenders']}\n"
        f"Suspicious inbound (just-under-threshold) txns: {account['suspiciousInboundCount']}\n"
        f"Total outbound: ${account['totalOut']:,.2f}\n"
        f"Part of a circular flow: {'Yes' if account['inCircularFlow'] else 'No'}"
    )


def send_slack_alert(message):
    if not SLACK_ENABLED:
        return
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
        if response.status_code != 200:
            print(f"  [Slack] Failed to send alert: {response.status_code} {response.text}")
    except requests.RequestException as e:
        print(f"  [Slack] Error sending alert: {e}")


def send_email_alert(subject, message):
    if not EMAIL_ENABLED:
        return
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [EMAIL_TO], msg.as_string())
    except Exception as e:
        print(f"  [Email] Error sending alert: {e}")


def run_alert_loop():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    print(f"FinGraph alert engine started. Checking every {CHECK_INTERVAL_SECONDS}s, threshold={RISK_THRESHOLD}.\n")

    try:
        while True:
            high_risk = get_high_risk_accounts(driver, RISK_THRESHOLD)
            new_alerts = [a for a in high_risk if a["account"] not in already_alerted]

            if new_alerts:
                for account in new_alerts:
                    message = format_message(account)
                    print(f"[ALERT] {account['account']} scored {account['riskScore']}/100")
                    send_slack_alert(message)
                    send_email_alert(
                        f"FinGraph Alert: {account['account']} scored {account['riskScore']}/100",
                        message,
                    )
                    already_alerted.add(account["account"])
            else:
                print("No new high-risk accounts this cycle.")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nAlert engine stopped.")
    finally:
        driver.close()


if __name__ == "__main__":
    run_alert_loop()