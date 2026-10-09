import re
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import random

import tictactoe
import minesweeper

app = FastAPI()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER = "games@games.jackjacobson2011.com"


async def send_email_reply(to_address: str, subject: str, text_content: str, message_id: str = None):
    """Sends outbound email reply w/ Resend API."""
    if not RESEND_API_KEY:
        print("Didn't get API key from environment")
        return

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    headers = {"Auto-Submitted": "auto-replied"}
    if message_id:
        msg_id = message_id if message_id.startswith("<") else f"<{message_id}>"
        headers["In-Reply-To"] = msg_id
        headers["References"] = msg_id

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


@app.get("/")
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/api/stats")
async def get_stats():
    return {
        "tictactoe": tictactoe.get_all_stats(),
        "minesweeper": minesweeper.get_all_ms_stats()
    }


@app.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    payload = await request.json()

    data = payload.get("data", {})
    sender = data.get("from", "No sender found")
    subject = data.get("subject", "No subject found")
    email_id = data.get("email_id")
    message_id = data.get("message_id")

    print(f'GOT EMAIL from "{sender}" with subject "{subject}" and id "{email_id}"')

    body = ""

    if email_id and RESEND_API_KEY:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.resend.com/emails/receiving/{email_id}",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"}
            )
            if res.status_code == 200:
                email_detail = res.json()
                body = email_detail.get("text") or email_detail.get("html") or "No body received"

    print(f"BODY:\n{body}")

    # Determine game choice from Subject, Body, or Move Coordinates
    is_minesweeper = (
        bool(re.search(r"\b(mine|minesweeper|ms)\b", subject, re.IGNORECASE)) or
        bool(re.search(r"\b(mine|minesweeper|ms|flag|f\s+[a-e][1-5])\b", body, re.IGNORECASE)) or
        bool(re.search(r"\b([D-Ed-e][1-5]|[A-Ca-c][4-5])\b", body)) # Coordinates outside 3x3 Tic-Tac-Toe
    )

    if is_minesweeper:
        print("🎮 Routing to Minesweeper Engine")
        reply_msg = minesweeper.process_ms_move(sender, body)
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}

    # Default to Tic-Tac-Toe
    print("🎮 Routing to Tic-Tac-Toe Engine")
    has_move = re.search(r"\b([A-Ca-c][1-3])\b", body)
    board, status = tictactoe.get_or_create_game(sender)

    if not has_move:
        reply_msg = (
            f"Welcome to Play-by-Email Games!\n\n"
            f"To play Tic-Tac-Toe, reply with coordinates (e.g. A1, B2).\n"
            f"To play Minesweeper, put 'Minesweeper' in the subject or reply 'Minesweeper'.\n\n"
            f"Current Tic-Tac-Toe Board:\n\n{tictactoe.format_board(board)}"
        )
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}

    user_move = has_move.group(1).upper()
    idx = tictactoe.MOVE_MAP[user_move]

    if board[idx] != "_":
        reply_msg = f"Position {user_move} is already taken!\n\n{tictactoe.format_board(board)}"
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}

    board_list = list(board)
    board_list[idx] = "X"
    board = "".join(board_list)

    winner = tictactoe.check_winner(board)
    if winner == 'X':
        tictactoe.update_game(sender, board, status="WON")
        tictactoe.record_stat(sender, "WON")
        msg = f"Congrats! You won!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    if winner == 'DRAW':
        tictactoe.update_game(sender, board, status="DRAW")
        tictactoe.record_stat(sender, "DRAW")
        msg = f"It's a draw!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    empty_indexes = [i for i, char in enumerate(board) if char == "_"]
    bot_index = random.choice(empty_indexes)
    board_list[bot_index] = 'O'
    board = "".join(board_list)

    winner = tictactoe.check_winner(board)
    if winner == 'O':
        tictactoe.update_game(sender, board, status="LOST")
        tictactoe.record_stat(sender, "LOST")
        msg = f"The bot won!\n\n{tictactoe.format_board(board)}\n\nReply with a move to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    tictactoe.update_game(sender, board, status="ACTIVE")
    bot_coord = list(tictactoe.MOVE_MAP.keys())[list(tictactoe.MOVE_MAP.values()).index(bot_index)]

    reply_msg = (
        f"You played {user_move}. Bot played {bot_coord}.\n\n"
        f"{tictactoe.format_board(board)}\n\n"
        f"Your turn! Reply with your next move."
    )
    await send_email_reply(sender, subject, reply_msg, message_id)
    return {"status": "success"}