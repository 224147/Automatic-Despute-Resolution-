"""Standalone RabbitMQ consumer for the demo broker.

Only meaningful when RABBITMQ_ENABLED=true and a broker is reachable (see
docker-compose.yml). When disabled, events/dispatch.py already runs the same
consumers synchronously in-process, so this script is optional for the demo.

Run with: python -m events.consumer_runner
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

import pika

from events.consumers import audit_consumer, notification_consumer

QUEUE = "banking.events"


def handle_message(channel, method, properties, body):
    event = json.loads(body)
    audit_consumer(event)
    notification_consumer(event)
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
    if os.getenv("RABBITMQ_ENABLED", "false").lower() != "true":
        print("RABBITMQ_ENABLED is not true — nothing to consume. Events are handled in-process instead.")
        return
    connection = pika.BlockingConnection(pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.basic_consume(queue=QUEUE, on_message_callback=handle_message)
    print("Consumer running. Waiting for events on 'banking.events'...")
    channel.start_consuming()


if __name__ == "__main__":
    main()
