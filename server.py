from flask import Flask, request, jsonify, Response
import os
import json
import atexit
from datetime import datetime
import secrets  # for unbiased random selection

GAMES_FILE = "games.json"
PAIRS_FILE = "pairs.json"   # new: persistent color history per device pair

app = Flask(__name__)
games = {}
pairs = {}  # key: "devA|devB" (sorted); value: {"last_white": "<device_id>"}

# ---------- Persistence ----------

def save_games():
    try:
        with open(GAMES_FILE, "w") as f:
            json.dump(games, f)
        print("📎 Game data saved to disk.")
    except Exception as e:
        print(f"❌ Failed to save game data: {e}")

def load_games():
    global games
    if os.path.exists(GAMES_FILE):
        try:
            with open(GAMES_FILE, "r") as f:
                games.update(json.load(f))
            print("📅 Game data loaded from disk.")
        except Exception as e:
            print(f"❌ Failed to load game data: {e}")

def save_pairs():
    try:
        with open(PAIRS_FILE, "w") as f:
            json.dump(pairs, f)
        print("📎 Pair history saved to disk.")
    except Exception as e:
        print(f"❌ Failed to save pair history: {e}")

def load_pairs():
    global pairs
    if os.path.exists(PAIRS_FILE):
        try:
            with open(PAIRS_FILE, "r") as f:
                pairs.update(json.load(f))
            print("🤝 Pair history loaded from disk.")
        except Exception as e:
            print(f"❌ Failed to load pair history: {e}")

load_games()
load_pairs()

def mutate(fn, *args, **kwargs):
    """Run a mutation, then persist."""
    result = fn(*args, **kwargs)
    # Persist both structures on any state change
    save_games()
    save_pairs()
    return result

# ---------- Helpers ----------

def pair_key(a: str, b: str) -> str:
    """Stable key for a pair of device IDs, order-independent."""
    if a is None or b is None:
        return None
    return "|".join(sorted([str(a), str(b)]))

def auto_assign_colors(game):
    """Assign colors based on pair history (random first time, alternate thereafter)."""
    owners = game.get("owners", [])
    if len(owners) != 2:
        return False

    a, b = owners[0], owners[1]
    key = pair_key(a, b)
    if not key:
        return False

    last = pairs.get(key, {}).get("last_white")

    if last == a:
        white, black = b, a
    elif last == b:
        white, black = a, b
    else:
        # first time: random
        white = secrets.choice([a, b])
        black = b if white == a else a

    game["white_player"] = white
    game["black_player"] = black
    game["color_chosen"] = True
    game["plays_as_white"] = None  # legacy hint no longer meaningful
    game["turn"] = "white"         # standard chess rule
    game["winner"] = None
    game["result"] = None

    # record new "last_white" for this pair so next time we flip
    pairs[key] = {"last_white": white}
    return True

def get_color_for_device(game, device_id):
    if game.get("white_player") == device_id:
        return "white"
    if game.get("black_player") == device_id:
        return "black"
    return None

def ensure_two_players(game):
    owners = game.get("owners", [])
    return len(owners) == 2 and game.get("white_player") and game.get("black_player")

def game_is_over(game):
    return bool(game.get("winner")) or bool(game.get("result"))

def minimal_pgn_from_uci(game_id, game):
    """Build a minimal PGN-like export from UCI (or simple) moves.
    We do NOT convert to SAN; we just number them as '1. e2e4 e7e5 2. g1f3 ...'"""
    moves = game.get("moves", [])
    white_name = game.get("usernames", [""])[0] if game.get("usernames") else ""
    black_name = ""
    # Try to find black username
    owners = game.get("owners", [])
    usernames = game.get("usernames", [])
    if game.get("black_player") in owners:
        try:
            idx = owners.index(game.get("black_player"))
            if 0 <= idx < len(usernames):
                black_name = usernames[idx]
        except ValueError:
            pass

    result = game.get("result") or "*"
    tags = [
        f'[Event "ESP32 Online Chess"]',
        f'[Site "Render/Flask"]',
        f'[Date "{datetime.utcnow().strftime("%Y.%m.%d")}"]',
        f'[Round "-"]',
        f'[White "{white_name}"]',
        f'[Black "{black_name}"]',
        f'[Result "{result}"]',
        f'[GameId "{game_id}"]'
    ]
    # Number the moves: white move starts at index 0
    body_parts = []
    for i, mv in enumerate(moves):
        if i % 2 == 0:
            body_parts.append(f"{(i//2)+1}. {mv}")
        else:
            body_parts.append(f"{mv}")
    body = " ".join(body_parts)
    if result != "*":
        body = (body + " " + result).strip()
    return "\n".join(tags) + "\n\n" + body + "\n"

# ---------- Core Routes ----------

@app.route('/ping', methods=['GET'])
def ping():
    return 'pong', 200

@app.route("/start", methods=["POST"])
def start_game():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        device_id = data.get("device_id")
        username = data.get("username")
        pin = data.get("pin")  # Optional PIN to make this a private game

        if not game_id or not device_id:
            return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

        if game_id not in games:
            games[game_id] = {
                "owners": [device_id],
                "usernames": [username or ""],
                "moves": [],                    # keep as list[str] for device compatibility
                "history": [],                  # optional richer history
                "pin": pin or None,             # presence => private game
                "color_chosen": False,
                "plays_as_white": None,         # legacy hint for older clients
                "white_player": None,
                "black_player": None,
                "opponent": "",
                "turn": None,                   # "white" or "black" once both joined
                "created": datetime.utcnow().isoformat(),
                "winner": None,                 # device_id of winner if finished
                "result": None                  # "1-0","0-1","1/2-1/2"
            }
            return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

        game = games[game_id]

        if device_id in game["owners"]:
            return jsonify({"status": "ok", "message": "Rejoined your own game"})

        if len(game["owners"]) >= 2:
            return jsonify({"status": "error", "message": "Game already has two players"}), 403

        return jsonify({"status": "error", "message": "Use /join to enter an open or private game"}), 400

    return mutate(_impl)

@app.route("/join", methods=["POST"])
def join_game():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        device_id = data.get("device_id")
        username = data.get("username")
        pin = data.get("pin")              # Optional, required if game has a PIN

        if not game_id or not device_id:
            return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]

        if game_is_over(game):
            return jsonify({"status": "error", "message": "Game already finished"}), 409

        # Private game enforcement
        if game.get("pin") and pin != game["pin"]:
            return jsonify({"status": "error", "message": "Incorrect or missing invitation PIN"}), 403

        if device_id in game["owners"]:
            return jsonify({"status": "ok", "message": "Already in this game"})

        if len(game["owners"]) >= 2:
            return jsonify({"status": "error", "message": "Game already has two players"}), 403

        # Accept join
        game["owners"].append(device_id)
        game["usernames"].append(username or "")
        # Color is arbitrated by server now
        auto_assign_colors(game)

        # Opponent (for creator’s view)
        game["opponent"] = username or ""

        print(f"🎯 Game '{game_id}' joined by {username}. Assigned: W={game.get('white_player')} B={game.get('black_player')}")
        return jsonify({"status": "ok", "message": f"Joined game '{game_id}' successfully"})

    return mutate(_impl)

@app.route("/move", methods=["POST"])
def post_move():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        move = data.get("move")
        device_id = data.get("device_id")

        if not game_id or not move or not device_id:
            return jsonify({"status": "error", "message": "Missing fields"}), 400

        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]

        if "owners" not in game or device_id not in game["owners"]:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        if game_is_over(game):
            return jsonify({"status": "error", "message": "Game already finished"}), 409

        if not ensure_two_players(game):
            return jsonify({"status": "error", "message": "Game not ready (waiting for both players)"}), 409

        # Enforce server-side turn
        color = get_color_for_device(game, device_id)
        if color is None:
            return jsonify({"status": "error", "message": "Player color not assigned"}), 409

        if game.get("turn") != color:
            return jsonify({"status": "error", "message": f"Not {color}'s turn"}), 409

        # Record (keep string list for devices)
        game["moves"].append(move)
        # Optional richer history with metadata
        game["history"].append({
            "idx": len(game["moves"]),
            "move": move,
            "by": device_id,
            "color": color,
            "ts": datetime.utcnow().isoformat()
        })

        # Flip turn
        game["turn"] = "black" if color == "white" else "white"

        print(f"🎮 MOVE {len(game['moves'])}: {game_id} | {device_id} ({color}) -> {move} | next: {game['turn']}")
        return jsonify({"status": "ok", "message": f"Move '{move}' recorded", "next_turn": game["turn"]})

    return mutate(_impl)

@app.route("/lastmove", methods=["GET"])
def get_last_move():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    if not games[game_id]["moves"]:
        return jsonify({"status": "ok", "move": None})
    return jsonify({"status": "ok", "move": games[game_id]["moves"][-1]})

@app.route("/moves", methods=["GET"])
def get_move_list():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    return jsonify({"status": "ok", "moves": games[game_id]["moves"]})

@app.route("/reset", methods=["POST"])
def reset_game():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        device_id = data.get("device_id")

        if not game_id or not device_id:
            return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]

        if "owners" not in game or device_id not in game["owners"]:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        game["moves"] = []
        game["history"] = []
        # If colors are assigned, white moves next; otherwise None
        game["turn"] = "white" if ensure_two_players(game) else None
        game["winner"] = None
        game["result"] = None

        print(f"🔄 Game '{game_id}' has been reset by {device_id}")
        print(f"🎮 Game '{game_id}' moves: {game['moves']}")
        return jsonify({"status": "ok", "message": f"Game '{game_id}' reset", "turn": game["turn"]})

    return mutate(_impl)

@app.route("/games", methods=["GET"])
def list_games():
    return jsonify({"status": "ok", "games": list(games.keys())})

@app.route("/status")
def game_status():
    game_id = request.args.get("game_id")
    device_id = request.args.get("device_id")  # optional to compute your_turn
    game = games.get(game_id)

    if not game:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    owners = game.get("owners", [])
    white_player = game.get("white_player")
    black_player = game.get("black_player")
    turn = game.get("turn")

    payload = {
        "status": "ok",
        "game_id": game_id,
        "owners": owners,
        "usernames": game.get("usernames", []),
        "opponent": game.get("opponent", ""),
        "move_count": len(game.get("moves", [])),
        "plays_as_white": game.get("plays_as_white", None),  # legacy hint
        "white_player": white_player,
        "black_player": black_player,
        "turn": turn,
        "last_move": game["moves"][-1] if game["moves"] else None,
        "winner": game.get("winner"),
        "result": game.get("result")
    }

    if len(owners) < 2 or not white_player or not black_player:
        payload["message"] = "Game incomplete"

    if device_id:
        color = get_color_for_device(game, device_id)
        payload["your_color"] = color
        payload["your_turn"] = (color is not None and turn == color and not game_is_over(game))

    return jsonify(payload)

@app.route("/delete", methods=["POST"])
def delete_game():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        device_id = data.get("device_id")

        if not game_id or not device_id:
            return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]
        if device_id not in game.get("owners", []):
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        del games[game_id]
        print(f"❌ Game '{game_id}' deleted by {device_id}")
        return jsonify({"status": "ok", "message": f"Game '{game_id}' deleted"})

    return mutate(_impl)

@app.route("/games/open", methods=["GET"])
def list_open_games():
    open_games = []
    for game_id, game in games.items():
        # Only list games with exactly one owner, no color chosen,
        # and NOT private (no PIN)
        if (
            len(game.get("owners", [])) == 1 and
            not game.get("color_chosen", False) and
            not game.get("pin")
        ):
            open_games.append({
                "game_id": game_id,
                "username": game.get("usernames", [""])[0],
                "created": game.get("created")
            })
    return jsonify({"status": "ok", "open_games": open_games})

@app.route("/games/resume", methods=["GET"])
def resume_my_games():
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400

    resumed = []
    for game_id, game in games.items():
        if (
            device_id in game.get("owners", []) and
            game.get("color_chosen") and
            len(game.get("owners", [])) == 2
        ):
            owners = game.get("owners", [])
            usernames = game.get("usernames", [])
            if device_id == game.get("white_player"):
                opp_id = game.get("black_player")
            else:
                opp_id = game.get("white_player")
            try:
                opp_index = owners.index(opp_id) if opp_id in owners else -1
                opp_name = usernames[opp_index] if 0 <= opp_index < len(usernames) else game.get("opponent", "")
            except ValueError:
                opp_name = game.get("opponent", "")

            resumed.append({
                "game_id": game_id,
                "opponent": opp_name,
                "plays_as_white": (game.get("white_player") == device_id),
                "move_count": len(game.get("moves", [])),
                "turn": game.get("turn"),
                "winner": game.get("winner"),
                "result": game.get("result")
            })

    return jsonify({"status": "ok", "resumable_games": resumed})

# ---------- Discrete Endpoints (unchanged, still useful) ----------

@app.route("/forfeit", methods=["POST"])
def forfeit_game():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        device_id = data.get("device_id")

        if not game_id or not device_id:
            return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400
        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]
        if device_id not in game.get("owners", []):
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        if game_is_over(game):
            return jsonify({"status": "error", "message": "Game already finished"}), 409

        owners = game.get("owners", [])
        if len(owners) < 2:
            return jsonify({"status": "error", "message": "Game has not started"}), 409

        # Winner is the other player
        winner_id = owners[0] if owners[1] == device_id else owners[1]
        game["winner"] = winner_id
        # Result depends on color of winner
        if winner_id == game.get("white_player"):
            game["result"] = "1-0"
        elif winner_id == game.get("black_player"):
            game["result"] = "0-1"
        else:
            game["result"] = "*"
        game["turn"] = None  # Game over

        print(f"🏳️ Forfeit: {device_id} forfeited in '{game_id}'. Winner: {winner_id}")
        return jsonify({"status": "ok", "message": f"Player forfeited; winner set", "winner": winner_id, "result": game["result"]})
    return mutate(_impl)

@app.route("/setcolor", methods=["POST"])
def set_color():
    def _impl():
        data = request.get_json()
        game_id = data.get("game_id")
        requester = data.get("device_id")  # must be an owner
        white_device_id = data.get("white_device_id")
        black_device_id = data.get("black_device_id")
        force = bool(data.get("force", False))  # allow overriding existing colors

        if not game_id or not requester or not white_device_id or not black_device_id:
            return jsonify({"status": "error", "message": "Missing fields"}), 400
        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]
        owners = game.get("owners", [])

        if requester not in owners:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403

        if not all(d in owners for d in (white_device_id, black_device_id)):
            return jsonify({"status": "error", "message": "Both players must be current owners"}), 400

        if (game.get("white_player") or game.get("black_player")) and not force:
            return jsonify({"status": "error", "message": "Colors already set; use force=true to override"}), 409

        game["white_player"] = white_device_id
        game["black_player"] = black_device_id
        game["color_chosen"] = True
        if len(owners) >= 2:
            game["plays_as_white"] = (white_device_id == owners[1])
        game["turn"] = "white"
        game["winner"] = None
        game["result"] = None

        # Keep pair history consistent with manual override
        key = pair_key(owners[0], owners[1]) if len(owners) == 2 else None
        if key:
            pairs[key] = {"last_white": white_device_id}

        print(f"🎨 Colors set for '{game_id}': W={white_device_id} B={black_device_id} (force={force})")
        return jsonify({"status": "ok", "message": "Colors assigned", "turn": game["turn"]})
    return mutate(_impl)

@app.route("/exportpgn", methods=["GET"])
def export_pgn():
    game_id = request.args.get("game_id")
    as_text = request.args.get("format", "json").lower() in ("txt", "text", "plain")
    if not game_id or game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    game = games[game_id]
    pgn_text = minimal_pgn_from_uci(game_id, game)

    if as_text:
        return Response(pgn_text, mimetype="text/plain")

    return jsonify({"status": "ok", "pgn": pgn_text})

# --- Administrative ---

@app.route("/admin/purge", methods=["POST"])
def purge_games():
    games.clear()
    save_games()
    return jsonify({"status": "ok", "message": "All games purged"})

@app.route("/admin/pairs", methods=["GET"])
def admin_list_pairs():
    """Optional helper to inspect color history."""
    return jsonify({"status": "ok", "pairs": pairs})

@app.route("/admin/pairs/clear", methods=["POST"])
def admin_clear_pairs():
    """Optional helper to reset color history."""
    pairs.clear()
    save_pairs()
    return jsonify({"status": "ok", "message": "Pair history cleared"})

atexit.register(save_games)
atexit.register(save_pairs)

if __name__ == "__main__":
    app.run(debug=True)
 
