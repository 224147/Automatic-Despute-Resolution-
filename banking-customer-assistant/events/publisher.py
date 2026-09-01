import json
import os


def publish(event_type: str, payload: dict) -> bool:
    """POC publisher: RabbitMQ is optional; return False when unavailable."""
    if os.getenv("RABBITMQ_ENABLED", "false").lower() != "true":
        return False
    try:
        import pika
        connection = pika.BlockingConnection(pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")))
        channel = connection.channel(); channel.queue_declare(queue="banking.events", durable=True)
        channel.basic_publish(exchange="", routing_key="banking.events", body=json.dumps(payload))
        connection.close(); return True
    except Exception:
        return False
