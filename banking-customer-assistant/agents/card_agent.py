from mock_banking.data import get_cards, card_for_customer


def cards(customer_id):
    return get_cards(customer_id)


def ownership(customer_id, last4):
    return card_for_customer(customer_id, last4)[0] is not None


def lookup(customer_id, last4):
    """Return the card owned by this customer, or None if not found/not owned."""
    _, card = card_for_customer(customer_id, last4)
    return card


def handle(customer_id, intent, last4):
    """Compose a safe confirmation/edge-case response for a block/unblock request.

    Actual state mutation happens only via the explicit /cards/block or
    /cards/unblock endpoint after the user confirms — this just validates
    and describes what would happen.
    """
    if not last4:
        return {"response": "Which card would you like to manage? Please share the last 4 digits.", "current_step": "Awaiting Card Number"}

    card = lookup(customer_id, last4)
    if not card:
        return {"response": f"I couldn't find a card ending {last4} on your account.", "current_step": "Card Not Found"}

    if card.get("expired"):
        return {"response": f"Card ending {last4} has expired and can't be blocked or unblocked. Please contact a representative for a replacement.", "current_step": "Card Expired"}

    if intent == "block_card":
        if card["status"] == "BLOCKED":
            return {"response": f"Card ending {last4} is already blocked.", "current_step": "Already Blocked"}
        return {
            "response": f"Card ending {last4}\n\nCurrent status: {card['status']}\n\nYou are about to block this card. This will prevent further card transactions.",
            "current_step": "Awaiting Confirmation",
            "pending_card": last4,
        }

    if intent == "unblock_card":
        if card["status"] == "ACTIVE":
            return {"response": f"Card ending {last4} is already active.", "current_step": "Already Active"}
        return {
            "response": f"Card ending {last4}\n\nCurrent status: {card['status']}\n\nYou are about to unblock this card.",
            "current_step": "Awaiting Confirmation",
            "pending_unblock_card": last4,
        }

    return {"response": "I couldn't process that card request.", "current_step": "Unhandled"}
