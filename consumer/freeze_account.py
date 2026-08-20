"""
FinGraph — Freeze Account Action
Marks a flagged account (and optionally its whole connected syndicate)
as frozen in Neo4j. This is the "analyst freezes the syndicate with
one click" action from the use case.

Usage:
    python freeze_account.py ACC1234ABCD          -> freeze just this account
    python freeze_account.py ACC1234ABCD --cluster -> freeze this account
                                                        AND everyone who sent
                                                        it money (the syndicate)
"""

import sys
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "fingraph123"


def freeze_single_account(driver, account_id):
    """Freezes just the one flagged account."""
    query = """
    MATCH (a:Account {account_id: $account_id})
    SET a.frozen = true, a.frozen_at = datetime(), a.frozen_reason = 'Starburst pattern detected'
    RETURN a.account_id AS account, a.frozen AS frozen, a.frozen_at AS frozen_at
    """
    with driver.session() as session:
        result = session.run(query, account_id=account_id)
        record = result.single()
        return record


def freeze_syndicate(driver, account_id):
    """
    Freezes the flagged account AND every account that sent money
    directly into it — the whole detected syndicate, not just the hub.
    """
    query = """
    MATCH (sender:Account)-[:TRANSFERRED_TO]->(hub:Account {account_id: $account_id})
    SET hub.frozen = true, hub.frozen_at = datetime(), hub.frozen_reason = 'Starburst hub account'
    WITH hub, collect(sender) AS senders
    UNWIND senders AS sender
    SET sender.frozen = true, sender.frozen_at = datetime(), sender.frozen_reason = 'Part of flagged syndicate'
    RETURN hub.account_id AS hubAccount, count(sender) AS frozenSenders
    """
    with driver.session() as session:
        result = session.run(query, account_id=account_id)
        record = result.single()
        return record


def unfreeze_account(driver, account_id):
    """Reverses a freeze — useful if an account was flagged in error."""
    query = """
    MATCH (a:Account {account_id: $account_id})
    REMOVE a.frozen, a.frozen_at, a.frozen_reason
    RETURN a.account_id AS account
    """
    with driver.session() as session:
        result = session.run(query, account_id=account_id)
        return result.single()


def list_frozen_accounts(driver):
    """Shows everything currently frozen — for verification/demo."""
    query = """
    MATCH (a:Account {frozen: true})
    RETURN a.account_id AS account, a.frozen_at AS frozenAt, a.frozen_reason AS reason
    ORDER BY a.frozen_at DESC
    """
    with driver.session() as session:
        result = session.run(query)
        return [dict(r) for r in result]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python freeze_account.py ACCOUNT_ID [--cluster]")
        print("       python freeze_account.py --list   (show all frozen accounts)")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    if sys.argv[1] == "--list":
        frozen = list_frozen_accounts(driver)
        if not frozen:
            print("No accounts currently frozen.")
        else:
            print(f"{len(frozen)} frozen account(s):\n")
            for f in frozen:
                print(f"  {f['account']} — frozen at {f['frozenAt']} ({f['reason']})")

    else:
        account_id = sys.argv[1]
        freeze_whole_cluster = "--cluster" in sys.argv

        if freeze_whole_cluster:
            result = freeze_syndicate(driver, account_id)
            if result:
                print(
                    f"Froze hub account {result['hubAccount']} "
                    f"and {result['frozenSenders']} connected sender accounts."
                )
            else:
                print(f"Account {account_id} not found.")
        else:
            result = freeze_single_account(driver, account_id)
            if result:
                print(f"Account {result['account']} frozen at {result['frozen_at']}.")
            else:
                print(f"Account {account_id} not found.")

    driver.close()
