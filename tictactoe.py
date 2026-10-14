import re
import os
import sqlite3
import random

DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "games.db")

RESET_DB = os.environ.get("RESET_DB", "false").lower() == "true"


# Setup database file with sqlite
def init_db():
    """Initialize SQLite databse for storing games"""
    with sqlite3.connect(DB_PATH) as con:

        if RESET_DB:
            con.execute("DROP TABLE IF EXISTS games")
            con.execute("DROP TABLE IF EXISTS stats")
            con.commit()
            
        con.execute("""
            CREATE TABLE IF NOT EXISTS games (
                player_email TEXT PRIMARY KEY,
                board TEXT DEFAULT '_________',
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                player_email TEXT PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                total_games INTEGER DEFAULT 0
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


def record_stat(email: str, result: str):
    """Record lifetime stats for a player"""
    wins_inc = 1 if result == "WON" else 0
    losses_inc = 1 if result == "LOST" else 0
    draws_inc = 1 if result == "DRAW" else 0

    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            INSERT INTO stats (player_email, wins, losses, draws, total_games)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(player_email) DO UPDATE SET
                wins = wins + ?,
                losses = losses + ?,
                draws = draws + ?,
                total_games = total_games + 1
        """, (email, wins_inc, losses_inc, draws_inc, wins_inc, losses_inc, draws_inc))
        con.commit()


def get_all_stats():
    """Get all user stats for the website dashboard"""
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute("""
            SELECT player_email, wins, losses, draws, total_games
            FROM stats
            ORDER BY wins DESC, total_games ASC
        """)
        rows = cursor.fetchall()
        return [
            {
                "email": r[0],
                "wins": r[1],
                "losses": r[2],
                "draws": r[3],
                "total_games": r[4]
            }
            for r in rows
        ]


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

def find_winning_move(board: str, player: str):
    """Returns index that winds for player or None"""
    for combo in WIN_COMBOS:
        vals = [board[i] for i in combo]
        if vals.count(player) == 2 and vals.count("_") == 1:
            return combo[vals.index("_")]
    return None

def minimax(board: str, is_maximizing: bool):
    """Recursivly solves for best possible movee and returns it"""
    winner = check_winner(board)
    if winner == "O":
        return 1
    if winner == "X":
        return -1
    if winner == "DRAW":
        return 0

    empty = [i for i, c in enumerate(board) if c == "_"]
    if is_maximizing:
        best = -100
        for idx in empty:
            b2 = board[:idx] + "O" + board[idx+1:]
            best = max(best, minimax(b2, False))
        return best
    else:
        best = 100
        for idx in empty:
            b2 = board[:idx] + "X" + board[idx+1:]
            best = min(best, minimax(b2, True))
        return best

def get_bot_move(board: str, difficulty: int = 1):
    empty_indexes = [i for i, char in enumerate(board) if char == "_"]

    #Random for level 1
    if difficulty ==1:
        return random.choice(empty_indexes)

    # Will alwayss win or block, otherwise random for level 2
    if difficulty == 2:
        win_move = find_winning_move(board, "O")
        if win_move is not None:
            return win_move
        block_move = find_winning_move(board, "X")
        if block_move is not None:
            return block_move
        return random.choice(empty_indexes)
    
    # Minmax to literally never lose for level 3:
    best_score = -100
    best_moves = []
    for idx in empty_indexes:
        next_board = board[:idx] + "O" + board[idx+1:]
        score = minimax(next_board, False)
        if score > best_score:
            best_score = score
            best_moves = [idx]
        elif score == best_score:
            best_moves.append(idx)
    return random.choice(best_moves) 

def format_board(board: str):
    """Format string board into ASCII grid"""
    b = [cell if cell != "_" else "." for cell in board]
    return (
        f"     1   2   3\n"
        f"A    {b[0]} | {b[1]} | {b[2]}\n"
        f"    ---+---+---\n"
        f"B    {b[3]} | {b[4]} | {b[5]}\n"
        f"    ---+---+---\n"
        f"C    {b[6]} | {b[7]} | {b[8]}\n"
    )