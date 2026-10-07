import re
import os
import httpx
import sqlite3
import random
from fastapi import FastAPI, Request

# Define API
app = FastAPI()

# Get api key from local environment variable
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Email that replies to messages 
SENDER = "games@games.jackjacobson2011.com"

# Database path from main.py
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "games.db")


# Setup database file with sqlite
def init_db():
    """Initialize SQLite databse for storing games"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS games (
                player_email TEXT PRIMARY KEY,
                board TEXT DEFAULT '_________',
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        con.commit()

init_db()

# Manage boards within the DB file
def get_or_create_game(email: str):
    """Retrieves existing game or creates a new game."""
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        # Trailing comma (email,) makes this a single-element tuple
        cursor.execute("SELECT board, status FROM games WHERE player_email = ?", (email,))
        row = cursor.fetchone()

        if not row or row[1] != 'ACTIVE':
            cursor.execute(
                "INSERT OR REPLACE INTO games (player_email, board, status) VALUES (?, '_________', 'ACTIVE')",
                (email,)
            )
            con.commit()
            return "_________", "ACTIVE"
        return row[0], row[1]

def update_game(email: str, board: str, status: str = 'ACTIVE'):
    """Update board states in db"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE games SET board = ?, status = ? WHERE player_email = ?", (board, status, email))
        con.commit()

MOVE_MAP = {
    "A1": 0, "A2": 1, "A3": 2,
    "B1": 3, "B2": 4, "B3": 5,
    "C1": 6, "C2": 7, "C3": 8
}
WIN_COMBOS = [
    [0,1,2], [3,4,5], [6,7,8], # Rows
    [0,3,6], [1,4,7], [2,5,8], # Columns
    [0,4,8], [2,4,6]           # Diagonals
]

def check_winner(board: str):
    """Checks if there is any win in supplied board"""
    for combo in WIN_COMBOS:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != '_':
            return board[combo[0]]
    if '_' not in board:
        return 'DRAW'
    return None

def format_board(board: str):
    """Format string board into ASCII grid"""
    b = [cell if cell != "_" else "." for cell in board]
    return (
        f"      1   2   3\n"
        f"A    {b[0]} | {b[1]} | {b[2]}\n"
        f"    ---+---+---\n"
        f"B    {b[3]} | {b[4]} | {b[5]}\n"
        f"    ---+---+---\n"
        f"C    {b[6]} | {b[7]} | {b[8]}\n"
    )
    

async def send_email_reply(to_address: str, subject: str, text_content: str, message_id:str = None):
    """Sneds outbound email reply w/ Resend API"""
    if not RESEND_API_KEY:
        print("Didn't get API key from environment")
        return

    # Add re to subject if not already existing
    if subject.lower().startswith("re:"):
        reply_subject = subject
    else:
        reply_subject = f"Re: {subject}"
    headers = {}
    if message_id:
        headers["In-Reply-To"] = message_id

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
    

# Health check
@app.get("/")
async def health_check():
    return{"status":"ok"}

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
    board, status = get_or_create_game(sender)

    # If no move found, send intro email and return
    if not has_move:
        reply_msg = (
            f"Welcome to Play-by-Email Tic-Tac-Toe!\n\n"
            f"Reply to this email with your move coordinates (e.g A1, C2)/ \n\n"
            f"Current Board: \n\n{format_board(board)}"
        )
        await send_email_reply(sender, subject, reply_msg, message_id)

        print(f"No valid move found, sent email:\n{reply_msg}")
        return {"status": "success"}

    # If move found:

    user_move = has_move.group(1).upper()
    idx = MOVE_MAP[user_move]

    # If move is placed in invalid spot, send email and return
    if board[idx] != "_":
        reply_msg = f"Position {user_move} is already taken!\n\n{format_board(board)}"
        await send_email_reply(sender, subject, reply_msg, message_id)

        print(f"Move placed invalidly, sent email:\n{reply_msg}")
        return {"status": "success"}

    # If move is palced in valid spot, place it
    board_list = list(board)
    board_list[idx] = "X"
    board = "".join(board_list)

    # Check winner and handle if X or Draw
    winner = check_winner(board)
    if winner == 'X':
        update_game(sender, board, status="WON")
        msg = f"Congats! You won!\n\n{format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user won, sent email:\n{msg}")
        return {"status": "success"}
    if winner == 'DRAW':
        update_game(sender, board, status="DRAW")
        msg = f"It's a draw!\n\n{format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user tied, sent email:\n{msg}")
        return {"status": "success"}

    # Random bot move at an empty index
    empty_indexes = [i for i, char in enumerate(board) if char == "_"]
    bot_index = random.choice(empty_indexes)
    board_list[bot_index] = 'O'
    board = "".join(board_list)

    # Check if bot one and send message if they did
    winner = check_winner(board)
    if winner =='O':
        update_game(sender, board, status="LOST")
        msg = f"The bot won!\n\n{format_board(board)}\n\nReply with a move to start a new game"
        await send_email_reply(sender, subject, msg, message_id)

        print(f"user lost, sent email:\n{msg}")
        return {"status": "success"}

    # Save state and reply with updated board
    update_game(sender, board, status="ACTIVE")
    bot_coord = list(MOVE_MAP.keys())[list(MOVE_MAP.values()).index(bot_index)]

    reply_msg = (
        f"You played {user_move}. Bot played {bot_coord}. \n\n"
        f"{format_board(board)}\n\n"
        f"Your turn! Reply with your next move."
    )
    await send_email_reply(sender, subject, reply_msg, message_id)

    print(f"user's turn, sent email:\n{reply_msg}") 
    return {"status": "success"}

