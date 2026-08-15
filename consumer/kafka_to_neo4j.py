"""
FinGraph — Kafka to Neo4j Consumer
Reads transaction events from Kafka and upserts them into Neo4j as
connected Account nodes with TRANSFERRED_TO relationships.

This also does simple in-memory threshold tracking as a stand-in for
Apache Flink's windowed aggregation — see the note in the guide about
why a plain Python consumer is a reasonable substitute for a solo build.
"""

import json
from collections import defaultdict

from kafka import KafkaConsumer
from neo4j import GraphDatabase

KAFKA_TOPIC = "transactions"
KAFKA_BROKER = "localhost:9092"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "fingraph123"

RISK_THRESHOLD = 9000  # flag accounts whose total outbound crosses this

# Tracks running outbound totals per sending account (in-memory, resets on restart)
outbound_totals = defaultdict(float)


def upsert_transaction(tx, sender_id, receiver_id, amount, timestamp):
    """Runs inside a Neo4j session — MERGE avoids creating duplicate nodes."""
    query = """
    MERGE (sender:Account {account_id: $sender_id})
    MERGE (receiver:Account {account_id: $receiver_id})
    MERGE (sender)-[t:TRANSFERRED_TO {
        transaction_id: $transaction_id,
        amount: $amount,
        timestamp: $timestamp
    }]->(receiver)
    RETURN sender, t, receiver
    """
    tx.run(
        query,
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=amount,
        timestamp=timestamp,
        transaction_id=timestamp + sender_id,  # simple unique-ish key
    )


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset="earliest",  # read from the beginning of the topic
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    print("Consumer started. Listening for transactions...\n")

    with driver.session() as session:
        for message in consumer:
            txn = message.value
            sender = txn["sender_account"]
            receiver = txn["receiver_account"]
            amount = txn["amount"]
            timestamp = txn["timestamp"]

            # Write to Neo4j
            session.execute_write(
                upsert_transaction, sender, receiver, amount, timestamp
            )
            print(f"Written to Neo4j: {sender} -> {receiver} : ${amount}")

            # Simple threshold check (stand-in for Flink windowed aggregation)
            outbound_totals[sender] += amount
            if outbound_totals[sender] > RISK_THRESHOLD:
                print(
                    f"  [ALERT] {sender} has sent over ${RISK_THRESHOLD} "
                    f"total (${outbound_totals[sender]:.2f}) — possible smurfing"
                )

    driver.close()


if __name__ == "__main__":
    main()
