from flask import Flask, request, jsonify
import os
import json
import atexit
from datetime import datetime

GAMES_FILE = "games.json"

app = Flask(__name__)
games = {}

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

load_games()

def mutate(fn, *args, **kwargs):
    """Run a mutation, then persist."""
    result = fn(*args, **kwargs)
    save_games()
    return result

# ---------- Helpers ----------

def get_color_for_device(game, device_id):
    if game.get("white_player") == device_id:
        return "white"
    if game.get("black_player") == device_id:
        return "black"
    return None

def ensure_two_players(game):
    owners = game.get("owners", [])
    return len(owners) == 2 and game.get("white_player") and game.get("black_player")

# ---------- Routes ----------

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
            # New game scaffold
            games[game_id] = {
                "owners": [device_id],
                "usernames": [username or ""],
                "moves": [],                    # keep as list[str] for device compatibility
                "history": [],                  # optional richer history
                "pin": pin or None,             # presence => private game
                "color_chosen": False,
                "plays_as_white": None,         # legacy hint for joiner choice
                "white_player": None,
                "black_player": None,
                "opponent": "",
                "turn": None,                   # "white" or "black" once both joined
                "created": datetime.utcnow().isoformat()
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
        plays_as_white = data.get("plays_as_white")  # Must be True/False

        if not game_id or not device_id or plays_as_white is None:
            return jsonify({"status": "error", "message": "Missing game_id, device_id, or color choice"}), 400

        if game_id not in games:
            return jsonify({"status": "error", "message": "Game not found"}), 404

        game = games[game_id]

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
        game["color_chosen"] = True
        game["plays_as_white"] = bool(plays_as_white)

        # Assign colors
        if plays_as_white:
            game["white_player"] = device_id
            game["black_player"] = game["owners"][0]
        else:
            game["white_player"] = game["owners"][0]
            game["black_player"] = device_id

        # Opponent (for creator’s view)
        game["opponent"] = username or ""

        # White to move first
        game["turn"] = "white"

        print(f"🎯 Game '{game_id}' joined by {username}, playing as {'White' if plays_as_white else 'Black'}")
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
    # Game not ready?
    if len(owners) < 2 or not game.get("white_player") or not game.get("black_player"):
        return jsonify({"status": "error", "message": "Game incomplete"}), 400

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
        "last_move": game["moves"][-1] if game["moves"] else None
    }

    if device_id:
        color = get_color_for_device(game, device_id)
        payload["your_color"] = color
        payload["your_turn"] = (color is not None and turn == color)

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
            # Determine opponent username if available
            owners = game.get("owners", [])
            usernames = game.get("usernames", [])
            if device_id == game.get("white_player"):
                opp_id = game.get("black_player")
            else:
                opp_id = game.get("white_player")
            try:
                opp_index = owners.index(opp_id) if opp_id in owners else -1
                opp_name = usernames[opp_index] if opp_index >= 0 and opp_index < len(usernames) else game.get("opponent", "")
            except ValueError:
                opp_name = game.get("opponent", "")

            resumed.append({
                "game_id": game_id,
                "opponent": opp_name,
                "plays_as_white": (game.get("white_player") == device_id),
                "move_count": len(game.get("moves", [])),
                "turn": game.get("turn")
            })

    return jsonify({"status": "ok", "resumable_games": resumed})

# --- Administrative ---

@app.route("/admin/purge", methods=["POST"])
def purge_games():
    games.clear()
    save_games()
    return jsonify({"status": "ok", "message": "All games purged"})

atexit.register(save_games)

if __name__ == "__main__":
    app.run(debug=True)
