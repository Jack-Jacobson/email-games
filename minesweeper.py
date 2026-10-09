import os
import re
import random
import sqlite3

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "games.db")

RESET_DB = os.environ.get("RESET_DB", "false").lower() == "true"

GRID_ROWS = 5
GRID_COLS = 5
NUM_MINS = 4
ROW_LABELS = ["A", "B", "C", "D", "E"]


def init_db():
    """Initialize sqlite tables for Minesweeper."""
    with sqlite3.connect(DB_PATH) as con:
        if RESET_DB:
            con.execute("DROP TABLE IF EXISTS ms_games")
            con.execute("DROP TABLE IF EXISTS ms_stats")
            con.commit()

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ms_games (
                player_email TEXT PRIMARY KEY,
                mines TEXT,
                state TEXT,
                status TEXT DEFAULT 'ACTIVE',
                first_move INTEGER DEFAULT 1
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ms_stats (
                player_email TEXT PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_games INTEGER DEFAULT 0
            )
            """
        )
        con.commit()


init_db()


def get_neighbors(idx: int):
    """Return valid neighboring indexes for a 5x5 board."""
    r, c = divmod(idx, GRID_COLS)
    neighbors = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS:
                neighbors.append(nr * GRID_COLS + nc)
    return neighbors


def generate_mines(exclude_idx: int = -1):
    """Generate random mine positions, excluding one safe starting cell."""
    all_indexes = [i for i in range(GRID_ROWS * GRID_COLS) if i != exclude_idx]
    mine_indexes = set(random.sample(all_indexes, NUM_MINS))
    return "".join("1" if i in mine_indexes else "0" for i in range(GRID_ROWS * GRID_COLS))


def get_or_create_ms_game(email: str):
    """Retrieves an existing active game or starts a new one."""
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute(
            "SELECT mines, state, status, first_move FROM ms_games WHERE player_email = ?",
            (email,),
        )
        row = cursor.fetchone()

        if not row or row[2] != "ACTIVE":
            initial_mines = generate_mines()
            initial_state = "_" * (GRID_COLS * GRID_ROWS)
            cursor.execute(
                "INSERT OR REPLACE INTO ms_games (player_email, mines, state, status, first_move) VALUES (?, ?, ?, 'ACTIVE', 1)",
                (email, initial_mines, initial_state),
            )
            con.commit()
            return initial_mines, initial_state, "ACTIVE", 1

        return row[0], row[1], row[2], row[3]


def update_ms_game(email: str, mines: str, state: str, status: str = "ACTIVE", first_move: int = 0):
    """Update a player’s Minesweeper game state in the database."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE ms_games SET mines = ?, state = ?, status = ?, first_move = ? WHERE player_email = ?",
            (mines, state, status, first_move, email),
        )
        con.commit()


def record_ms_stat(email: str, result: str):
    """Record lifetime Minesweeper stats."""
    wins_inc = 1 if result == "WON" else 0
    losses_inc = 1 if result == "LOST" else 0

    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO ms_stats (player_email, wins, losses, total_games)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(player_email) DO UPDATE SET
                wins = wins + excluded.wins,
                losses = losses + excluded.losses,
                total_games = total_games + 1
            """,
            (email, wins_inc, losses_inc),
        )
        con.commit()


def format_ms_board(state: str, reveal_all_mines: bool = False, mines: str = ""):
    """Format a 5x5 grid in ASCII."""
    header = "      1   2   3   4   5\n"
    rows_text = []

    for r in range(GRID_ROWS):
        row_str = f"{ROW_LABELS[r]}   "
        cells = []
        for c in range(GRID_COLS):
            idx = r * GRID_COLS + c
            char = state[idx]

            if reveal_all_mines and mines and mines[idx] == "1":
                display = "*"
            elif char == "_":
                display = "."
            elif char == "F":
                display = "F"
            else:
                display = char

            cells.append(f" {display}")

        row_str += "|".join(cells)
        rows_text.append(row_str)

    divider = "\n    ---+---+---+---+---\n"
    return header + divider.join(rows_text) + "\n"


def count_adjacent_mines(idx: int, mines: str):
    """Count adjacent mines for a given cell."""
    return sum(1 for neighbor in get_neighbors(idx) if mines[neighbor] == "1")


def cascade_reveal(idx: int, state_list: list, mines: str):
    """Reveal a region of empty cells around a chosen spot."""
    to_check = [idx]
    visited = set()

    while to_check:
        curr = to_check.pop()
        if curr in visited:
            continue
        visited.add(curr)

        if mines[curr] == "1":
            continue

        count = count_adjacent_mines(curr, mines)
        state_list[curr] = str(count)

        if count == 0:
            for neighbor in get_neighbors(curr):
                if state_list[neighbor] in ("_", "F") and neighbor not in visited:
                    to_check.append(neighbor)


def process_ms_move(email: str, body_text: str) -> str:
    """Process a player move (reveal, flag, or restart) and update game state."""
    if re.search(r"\b(NEW|RESET|RESTART)\b", body_text, re.IGNORECASE):
        mines = generate_mines()
        state = "_" * (GRID_ROWS * GRID_COLS)
        update_ms_game(email, mines, state, status="ACTIVE", first_move=1)
        return f"New Minesweeper Game Started!\n\n{format_ms_board(state)}\nReply with coordinates (e.g. A1, C3) or 'FLAG B2'."

    mines, state, status, is_first_move = get_or_create_ms_game(email)
    state_list = list(state)

    flag_match = re.search(r"\b(?:FLAG|F)\s*([A-Ea-e][1-5])\b", body_text, re.IGNORECASE)
    if flag_match:
        coord = flag_match.group(1).upper()
        r = ROW_LABELS.index(coord[0])
        c = int(coord[1]) - 1
        idx = r * GRID_COLS + c

        if state_list[idx] not in ("_", "F"):
            return f"Cell {coord} is already revealed!\n\n{format_ms_board(''.join(state_list))}"

        state_list[idx] = "F" if state_list[idx] == "_" else "_"
        new_state = "".join(state_list)
        update_ms_game(email, mines, new_state, status="ACTIVE", first_move=is_first_move)
        return f"Flag toggled at {coord}.\n\n{format_ms_board(new_state)}"

    move_match = re.search(r"\b([A-Ea-e][1-5])\b", body_text)
    if not move_match:
        return (
            f"Welcome to Email Minesweeper!\n\n"
            f"Commands:\n"
            f"• Reply with coordinates to reveal (e.g. A1, B3)\n"
            f"• Reply 'FLAG A1' or 'F A1' to flag a mine\n"
            f"• Reply 'NEW' to restart\n\n"
            f"Current Board:\n\n{format_ms_board(state)}"
        )

    coord = move_match.group(1).upper()
    r = ROW_LABELS.index(coord[0])
    c = int(coord[1]) - 1
    idx = r * GRID_COLS + c

    if is_first_move and mines[idx] == "1":
        mines = generate_mines(exclude_idx=idx)
        is_first_move = 0

    if mines[idx] == "1":
        update_ms_game(email, mines, state, status="LOST", first_move=0)
        record_ms_stat(email, "LOST")
        final_board = format_ms_board(state, reveal_all_mines=True, mines=mines)
        return f"💥 BOOM! You hit a mine at {coord}!\n\n{final_board}\nReply 'NEW' to play again."

    cascade_reveal(idx, state_list, mines)
    new_state = "".join(state_list)

    unrevealed_non_mines = sum(
        1 for i in range(GRID_ROWS * GRID_COLS)
        if mines[i] == "0" and new_state[i] in ("_", "F")
    )

    if unrevealed_non_mines == 0:
        update_ms_game(email, mines, new_state, status="WON", first_move=0)
        record_ms_stat(email, "WON")
        return f"🎉 You cleared all the mines! YOU WIN!\n\n{format_ms_board(new_state)}\nReply 'NEW' to play again."

    update_ms_game(email, mines, new_state, status="ACTIVE", first_move=0)
    return f"Revealed {coord}.\n\n{format_ms_board(new_state)}"


def get_all_ms_stats():
    """Retrieves Minesweeper stats for the website dashboard."""
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute(
            """
            SELECT player_email, wins, losses, total_games
            FROM ms_stats
            ORDER BY wins DESC, total_games ASC
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "email": r[0],
                "wins": r[1],
                "losses": r[2],
                "total_games": r[3],
            }
            for r in rows
        ]
