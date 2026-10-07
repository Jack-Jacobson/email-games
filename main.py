import re
from fastapi import FastAPI, Request

# Define API
app = FastAPI()

# Set up POST request 
@app.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    payload = await request.json()

    # Extract info from payload
    sender = payload.get("From") or payload.get("from") or "No sender recieved"
    subject = payload.get("Subject") or payload.get("subject") or "No subject recieved"
    body = payload.get("TextBody") or payload.get("text") or ""

    # Print payload to conssole
    print(f'GOT EMAIL from "{sender}" with subject "{subject}"')
    print(f'Body: {body}')

    # Temp - checks for a tic-tac-toe move
    has_move = re.search(r"\b([A-Ca-c][1-3])\b", body)

    if has_move:
        move = has_move.group(1).upper()
        print(f"Valid move at {move}")
    else:
        print("No valid move in body")

    return {"status": "success"}
    

