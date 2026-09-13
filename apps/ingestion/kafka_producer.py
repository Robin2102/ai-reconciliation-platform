"""
CONCEPT TO LEARN: producing events to Kafka vs. calling the next step directly.

Direct call: ingestion_task() -> reconciliation_task() (tight coupling)
Event-driven: ingestion_task() -> publish("record.ingested") -> anything
listening (now or in the future - even the AI agent later) can react.

TODO (together): wrap confluent_kafka.Producer with a simple `publish(topic, payload)`.
"""
# from confluent_kafka import Producer
