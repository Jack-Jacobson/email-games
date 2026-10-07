import re
import os
import httpx
from fastapi import FastAPI, Request

# Define API
app = FastAPI()

# Get api key from local environment variable
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Health check
@app.get("/")
async def health_check():
    return{"status":"ok"}

# Set up POST request 
@app.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    payload = await request.json()

    # Extract info from payload
    data = payload.get("data", {})
    sender = data.get("from", "No sender found")
    subject = data.get("subject", "No subject found")
    email_id = data.get("email_id")

    # Print payload to conssole
    print(f'GOT EMAIL from "{sender}" with subject "{subject} and id {email_id}"')

    body = ""

    # Extracts info from email given id and the api key
    if email_id and RESEND_API_KEY:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.resend.com/emails/receiving/{email_id}",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"}
            )
            if res.status_code == 200:
                email_detail = res.json()
                body = email_detail.get("text") or email_detail.get("html") or "No body recieved"
            else:
                print(f"Failed to get email content, HTTP status {res.status_code}: {res.text}")
    elif not RESEND_API_KEY:
        print("Didn't get API key from environment")
    else:
        print("Didnt get email id from webhook")

    print(f"BODY: \n{body}")

    # Checks for tic-tac-toe move
    has_move = re.search(r"\b([A-Ca-c][1-3])\b", body)

    if has_move:
        move = has_move.group(1).upper()
        print(f"Valid move at {move}")
    else:
        print("No valid move in body")

    return {"status": "success"}
    

