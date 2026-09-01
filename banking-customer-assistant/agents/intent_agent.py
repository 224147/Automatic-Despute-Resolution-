from backend.orchestrator import classify_intent

def classify(message: str):
    return classify_intent(message)
