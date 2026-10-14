import re
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import random
import html
import time

import tictactoe
import minesweeper

app = FastAPI()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER = "games@games.jackjacobson2011.com"

def extract_latest_reply(body: str):
    """Returns only user's new reply"""
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            break
        if re.match(r"^On .* wrote:$", stripped, re.IGNORECASE):
            break
        if stripped.startswith("From:") or stripped.startswith("-----Original Message"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


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

    clean_text = text_content.replace("```\n", "").replace("```", "")

    unique_id = str(int(time.time() * 1000))
    escaped_lines = [
        html.escape(line) + f'<span style="display:none">{unique_id}-{i}</span>'
        for i, line in enumerate(clean_text.splitlines())
    ]
    html_body = "\n".join(escaped_lines)

    html_content = f"""
    <div style="font-family: 'Courier New', Courier, monospace; font-size: 15px; line-height: 1.4; color: #111;">
      <pre style="font-family: 'Courier New', Courier, monospace; margin: 0; white-space: pre;">{html_body}</pre>
    </div>
    """
    
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
                "text": clean_text,
                "html": html_content,
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
    body = extract_latest_reply(body)

    print(f"BODY:\n{body}")

    is_reply = bool(re.match(r"^re:\s*", subject, re.IGNORECASE))
    clean_subject = re.sub(r"^re:\s*", "", subject, flags = re.IGNORECASE).strip()

    is_no_subject = not is_reply and (not subject or subject.strip() == "" or subject.lower() == "no subject found")

    if is_no_subject:
        print("Email recieved with no subject - sending welcome")
        reply_msg = (
            f"Welcome to Email Games!!\n"
            f"Your email did not include a valid subject line, include one of the below subjects to play!\n"
            f"How to play:\n"
            f"- Tic Tac Toe: put 'Tic-Tac-Toe' in your subject, select a difficulty (LEVEL 1, LEVEL 2, or LEVEL 3), and reply with coordinates A1-C3 (e.g. A3, C1)\n"
            f"- Minesweeper: put 'Minesweeper' in your subject and reply with coordinates A1-E5 or 'FLAG [COORD]'.\n"
        )
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}

    # Determine game choice from Subject, Body, or Move Coordinates
    is_minesweeper = (
        bool(re.search(r"\b(mine|minesweeper|ms)\b", subject, re.IGNORECASE)) or
        bool(re.search(r"\b(mine|minesweeper|ms|flag|f\s+[a-e][1-5])\b", body, re.IGNORECASE)) or
        bool(re.search(r"\b([D-Ed-e][1-5]|[A-Ca-c][4-5])\b", body)) # Coordinates outside 3x3 Tic-Tac-Toe
    )

    if is_minesweeper:
        print("Using minesweeper logic")
        reply_msg = minesweeper.process_ms_move(sender, body)
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}
    
    # Default to Tic-Tac-Toe
    print("Using tic tac toe logic")

    board, status, difficulty = tictactoe.get_or_create_game(sender)
    has_move = re.search(r"\b([A-Ca-c][1-3])\b", body)
    level_match = re.search(r"\b(?:LEVEL\s*([1-3])|(EASY|MEDIUM|HARD))\b", body, re.IGNORECASE)

    if level_match:
        if level_match.group(1):
            difficulty = int(level_match.group(1))
        else:
            word = level_match.group(2).upper()
            difficulty = {"EASY": 1, "MEDIUM": 2, "HARD": 3}[word]

        board = "_________"
        tictactoe.update_game(sender, board, status="ACTIVE", difficulty=difficulty)
        if not has_move:
            reply_msg = (
                f"Tic-Tac-Toe difficulty set to Level {difficulty}!\n\n"
                f"{tictactoe.format_board(board)}\n"
                f"Reply with coordinates (A1-C3) to make your first move."
            )
            await send_email_reply(sender, subject, reply_msg, message_id)
            return {"status": "success"}

    if difficulty not in (1, 2, 3):
        reply_msg = (
            f"Welcome to Tic-Tac-Toe!\n\n"
            f"Before starting, please select a difficulty level by replying with:\n"
            f"- LEVEL 1 (or EASY)\n"
            f"- LEVEL 2 (or MEDIUM)\n"
            f"- LEVEL 3 (or HARD)\n"
        )
        await send_email_reply(sender, subject, reply_msg, message_id)
        return {"status": "success"}

    if not has_move:
        reply_msg = (
            f"Welcome to Play-by-Email Games!\n\n"
            f"Current Difficulty: Level {difficulty}\n"
            f"To play Tic-Tac-Toe, reply with coordinates (e.g. A1, B2) or 'LEVEL 1-3' to change difficulty.\n"
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
        tictactoe.update_game(sender, board, status="WON", difficulty=difficulty)
        tictactoe.record_stat(sender, "WON")
        msg = f"Congrats! You won!\n\n{tictactoe.format_board(board)}\n\nReply with LEVEL 1, LEVEL 2, or LEVEL 3 to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    if winner == 'DRAW':
        tictactoe.update_game(sender, board, status="DRAW", difficulty=difficulty)
        tictactoe.record_stat(sender, "DRAW")
        msg = f"It's a draw!\n\n{tictactoe.format_board(board)}\n\nReply with LEVEL 1, LEVEL 2, or LEVEL 3 to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    bot_index = tictactoe.get_bot_move(board, difficulty)
    board_list[bot_index] = 'O'
    board = "".join(board_list)

    winner = tictactoe.check_winner(board)
    if winner == 'O':
        tictactoe.update_game(sender, board, status="LOST", difficulty=difficulty)
        tictactoe.record_stat(sender, "LOST")
        msg = f"The bot won!\n\n{tictactoe.format_board(board)}\n\nReply with LEVEL 1, LEVEL 2, or LEVEL 3 to start a new game."
        await send_email_reply(sender, subject, msg, message_id)
        return {"status": "success"}

    tictactoe.update_game(sender, board, status="ACTIVE", difficulty=difficulty)
    bot_coord = list(tictactoe.MOVE_MAP.keys())[list(tictactoe.MOVE_MAP.values()).index(bot_index)]

    reply_msg = (
        f"You played {user_move}. Bot played {bot_coord}.\n\n"
        f"{tictactoe.format_board(board)}\n\n"
        f"Your turn! Reply with your next move."
    )
    await send_email_reply(sender, subject, reply_msg, message_id)
    return {"status": "success"}