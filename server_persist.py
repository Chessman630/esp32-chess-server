from flask import Flask, request, jsonify
import os
import json
import atexit

GAMES_FILE = "games.json"


app = Flask(__name__)
games = {}

def save_games():
    try:
        with open(GAMES_FILE, "w") as f:
            json.dump(games, f)
        print("💾 Game data saved to disk.")
    except Exception as e:
        print(f"❌ Failed to save game data: {e}")

def load_games():
    global games
    if os.path.exists(GAMES_FILE):
        try:
            with open(GAMES_FILE, "r") as f:
                games.update(json.load(f))
            print("📥 Game data loaded from disk.")
        except Exception as e:
            print(f"❌ Failed to load game data: {e}")

load_games()

@app.route("/start", methods=["POST"])
def start_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")
    username = data.get("username")
    pin = data.get("pin")  # Optional PIN

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        # New game
        games[game_id] = {
            "owners": [device_id],
            "usernames": [username or ""],
            "moves": [],
            "pin": pin or None
        }
        return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

    game = games[game_id]

    if device_id in game["owners"]:
        return jsonify({"status": "ok", "message": "Rejoined your own game"})

    if len(game["owners"]) >= 2:
        return jsonify({"status": "error", "message": "Game already has two players"}), 403

    if game.get("pin"):
        if pin != game["pin"]:
            return jsonify({"status": "error", "message": "Incorrect or missing invitation PIN"}), 403

    # Add second player
    game["owners"].append(device_id)
    game["usernames"].append(username or "")
    return jsonify({"status": "ok", "message": "Joined game as second player"})









@app.route("/move", methods=["POST"])
def post_move():
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

    game["moves"].append(move)
    print(f"🎮 Game '{game_id}' moves: {game['moves']}")
    return jsonify({"status": "ok", "message": f"Move '{move}' recorded"})


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
    print(f"🔄 Game '{game_id}' has been reset by {device_id}")
    print(f"🎮 Game '{game_id}' moves: {game['moves']}")
    return jsonify({"status": "ok", "message": f"Game '{game_id}' reset"})

# ✅ Get full list of active game IDs (for listing or debug)
@app.route("/games", methods=["GET"])
def list_games():
    return jsonify({"status": "ok", "games": list(games.keys())})


# ✅ Get detailed status of a specific game
@app.route("/status", methods=["GET"])
def game_status():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    game = games[game_id]
    return jsonify({
        "status": "ok",
        "game_id": game_id,
        "owners": game.get("owners", []),
        "usernames": game.get("usernames", []),
        "move_count": len(game.get("moves", []))
    })

# ✅ Delete a game (only by an owner)
@app.route("/delete", methods=["POST"])
def delete_game():
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

@app.route("/games/open", methods=["GET"])
def list_open_games():
    open_games = []
    for game_id, game in games.items():
        if len(game.get("owners", [])) == 1:
            open_games.append({
                "game_id": game_id,
                "username": game.get("usernames", [""])[0]
            })
    return jsonify({"status": "ok", "open_games": open_games})

@app.route("/join", methods=["POST"])
def join_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")
    username = data.get("username")
    pin = data.get("pin")  # Optional PIN

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    game = games[game_id]

    if device_id in game["owners"]:
        return jsonify({"status": "ok", "message": "Rejoined your own game"})

    if len(game["owners"]) >= 2:
        return jsonify({"status": "error", "message": "Game already has two players"}), 403

    if game.get("pin"):
        if pin != game["pin"]:
            return jsonify({"status": "error", "message": "Incorrect or missing invitation PIN"}), 403

    game["owners"].append(device_id)
    game["usernames"].append(username or "")
    return jsonify({"status": "ok", "message": f"Joined game '{game_id}' as second player"})




atexit.register(save_games)

if __name__ == "__main__":
    app.run(debug=True)

