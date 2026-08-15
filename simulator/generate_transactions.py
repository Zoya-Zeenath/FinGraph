"""
FinGraph — Transaction Simulator
Generates fake accounts + transactions and streams them to Kafka as JSON.
Includes normal random traffic PLUS one deliberate "smurfing" pattern
so the detection queries later on have something real to catch.
"""

import json
import random
import time
import uuid
from datetime import datetime, timezone

from faker import Faker
from kafka import KafkaProducer

fake = Faker()

KAFKA_TOPIC = "transactions"
KAFKA_BROKER = "localhost:9092"

# ---- Setup Kafka producer ----
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)


def new_account_id():
    return "ACC" + str(uuid.uuid4())[:8].upper()


def send_transaction(sender_id, receiver_id, amount):
    """Build one transaction event and send it to Kafka."""
    txn = {
        "transaction_id": str(uuid.uuid4()),
        "sender_account": sender_id,
        "receiver_account": receiver_id,
        "amount": round(amount, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    producer.send(KAFKA_TOPIC, value=txn)
    print(f"Sent: {sender_id} -> {receiver_id} : ${txn['amount']}")


def generate_normal_traffic(account_pool, num_transactions=200):
    """Random, everyday-looking transfers between random accounts."""
    for _ in range(num_transactions):
        sender, receiver = random.sample(account_pool, 2)
        amount = round(random.uniform(10, 3000), 2)
        send_transaction(sender, receiver, amount)
        time.sleep(0.05)  # small delay so it streams instead of dumping instantly


def generate_smurfing_pattern(account_pool, num_smurfs=50):
    """
    The planted fraud pattern: many distinct accounts each send an amount
    just under the $10,000 reporting threshold into ONE shell account.
    This is what your Starburst detection query should catch later.
    """
    shell_account = new_account_id()
    print(f"\n--- Planting smurfing pattern into shell account {shell_account} ---\n")

    smurf_accounts = random.sample(account_pool, num_smurfs)
    for smurf in smurf_accounts:
        amount = round(random.uniform(9500, 9900), 2)  # just under $10,000
        send_transaction(smurf, shell_account, amount)
        time.sleep(0.05)

    return shell_account


if __name__ == "__main__":
    # Step 1: create a pool of fake accounts to transact between
    NUM_ACCOUNTS = 300
    accounts = [new_account_id() for _ in range(NUM_ACCOUNTS)]
    print(f"Generated {NUM_ACCOUNTS} fake accounts.\n")

    # Step 2: generate normal background traffic
    print("Generating normal transaction traffic...")
    generate_normal_traffic(accounts, num_transactions=200)

    # Step 3: plant the smurfing pattern
    shell = generate_smurfing_pattern(accounts, num_smurfs=50)

    # Step 4: a bit more normal traffic after, so the pattern isn't the last thing in the stream
    print("\nGenerating a bit more normal traffic...")
    generate_normal_traffic(accounts, num_transactions=50)

    producer.flush()
    print(f"\nDone. Shell account to look for later: {shell}")