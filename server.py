import re
import os
import httpx
import random
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import tictactoe

# Define API
app = FastAPI()

# Mount static files for HTML/CSS/JS frontend
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Get api key from local environment variable
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Email that replies to messages 
SENDER = "games@games.jackjacobson2011.com"


async def send_email_reply(to_address: str, subject: str, text_content: str, message_id: str = None):
    """Sneds outbound email reply w/ Resend API"""
    if not RESEND_API_KEY:
        print("Didn't get API key from environment")
        return

    # Add re to subject if not already existing
    if subject.lower().startswith("re:"):
        reply_subject = subject
    else:
        reply_subject = f"Re: {subject}"
    headers = {"Auto-Submitted": "auto-replied"}
    if message_id:
        msg_id = message_id if message_id.startswith("<") else f"<{message_id}>"
        headers["In-Reply-To"] = msg_id
        headers["References"] = msg_id

    # Send with Resend API
    # Can someone please tell me who JSON is?!??!?
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": SENDER,
                "to": [to_address],
                "subject": reply_subject,
                "text": text_content,
                "headers": headers
            },
        )

        if res.status_code == 200:
            print(f"Reply sent to {to_address}")
        else:
            print(f'Failed to send reply, HTTP {res.status_code}: {res.text}')


# Serve Dashboard Website
@app.get("/")
async def serve_dashboard():
    return FileResponse("static/index.html")


# API Endpoint for Dashboard JSON Stats
@app.get("/api/stats")
async def get_stats():
    return {"players": tictactoe.get_all_stats()}


# POST API call when email is forwared from ReSend
@app.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    payload = await request.json()

    # Extract info from payload
    data = payload.get("data", {})
    sender = data.get("from", "No sender found")
    subject = data.get("subject", "No subject found")
    email_id = data.get("email_id")
    message_id = data.get("message_id")

    # Print payload to conssole
    print(f'GOT EMAIL from "{sender}" with subject "{subject}" and id "{email_id}"')

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

    # Get active board
    board, status = tictactoe.get_or_create_game(sender)

    # If no move found, send intro email and return
    if not has_move:
        reply_msg = (
            f"Welcome to Play-by-Email Tic-Tac-Toe!\n\n"
            f"Reply to this email with your move coordinates (e.g A1, C2)/ \n\n"
            f"Current Board: \n\n{tictactoe.format_board(board)}"
        )
        await send_email_reply(sender, subject, reply_msg, message_id)

        print(f"No valid move found, sent email:\n{reply_msg}")
        return {"status": "success"}

    # If move found:

    user_move = has_move.group(1).upper()
    idx = tictactoe.MOVE_MAP[user_move]

    # If move is placed in invalid spot, send email and return
    if board[idx] != "_":
        reply_msg = f"Position {user_move} is already taken!\n\n{tictactoe.format_board(board)}"
        await send_email_reply(sender, subject, reply_msg, message_id)

        print(f"Move placed invalidly, sent email:\n{reply_msg}")
        return {"status": "success"}

    # If move is palced in valid spot, place it
    board_list = list(board)
    board_list[idx] = "X"
    board = "".join(board_list)

    # Check winner and handle if X or Draw
    winner = tictactoe.check_winner(board)
    if winner == 'X':
        tictactoe.update_game(sender, board, status="WON")
        tictactoe.record_stat(sender, "WON")
        msg = f"Congats! You won!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user won, sent email:\n{msg}")
        return {"status": "success"}
    if winner == 'DRAW':
        tictactoe.update_game(sender, board, status="DRAW")
        tictactoe.record_stat(sender, "DRAW")
        msg = f"It's a draw!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user tied, sent email:\n{msg}")
        return {"status": "success"}

    # Random bot move at an empty index
    empty_indexes = [i for i, char in enumerate(board) if char == "_"]
    bot_index = random.choice(empty_indexes)
    board_list[bot_index] = 'O'
    board = "".join(board_list)

    # Check if bot one and send message if they did
    winner = tictactoe.check_winner(board)
    if winner == 'O':
        tictactoe.update_game(sender, board, status="LOST")
        tictactoe.record_stat(sender, "LOST")
        msg = f"The bot won!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user lost, sent email:\n{msg}")
        return {"status": "success"}

    # Save state and reply with updated board
    tictactoe.update_game(sender, board, status="ACTIVE")
    bot_coord = list(tictactoe.MOVE_MAP.keys())[list(tictactoe.MOVE_MAP.values()).index(bot_index)]

    reply_msg = (
        f"You played {user_move}. Bot played {bot_coord}. \n\n"
        f"{tictactoe.format_board(board)}\n\n"
        f"Your turn! Reply with your next move."
    )
    await send_email_reply(sender, subject, reply_msg, message_id)

    print(f"user's turn, sent email:\n{reply_msg}") 
    return {"status": "success"}