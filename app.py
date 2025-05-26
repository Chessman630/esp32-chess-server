from flask import Flask, request, jsonify

app = Flask(__name__)
games = {}

@app.route("/start", methods=["POST"])
def start_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")
    username = data.get("username")

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        # New game, assign ownership
        games[game_id] = {
            "owners": [device_id],
            "usernames": [username or ""],
            "moves": []
        }
        return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

    # Game exists — check ownership
    existing = games[game_id]
    if device_id in existing["owners"]:
        return jsonify({"status": "ok", "message": "Rejoined your own game"})

    if len(existing["owners"]) >= 2:
        return jsonify({"status": "error", "message": "Game already has two players"}), 403

    # Add as second owner
    existing["owners"].append(device_id)
    existing["usernames"].append(username or "")
    return jsonify({"status": "ok", "message": "Joined as second player"})

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
    return jsonify({"status": "ok", "message": f"Move '{move}' recorded"})


@app.route("/lastmove", methods=["GET"])
def get_last_move():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    if not games[game_id]["moves"]:
        return jsonify({"status": "ok", "move": None})
    return jsonify({"status": "ok", "move": games[game_id]["moves"][-1]})

@app.route("/reset", methods=["POST"])
def reset_game():
    try:
        data = request.get_json()
        print("🔧 /reset called with:", data)

        game_id = data.get("game_id")
        if not game_id:
            return jsonify({"status": "error", "message": "Missing game_id"}), 400

        if game_id not in games:
            print(f"⚠️ Game '{game_id}' not found")
            return jsonify({"status": "error", "message": f"Game '{game_id}' not found"}), 404

        print(f"🧪 Type of games['{game_id}']: {type(games[game_id])}")
        print(f"🧪 Current game entry: {games[game_id]}")

        if isinstance(games[game_id], dict) and "moves" in games[game_id]:
            games[game_id]["moves"] = []
            print(f"✅ Game '{game_id}' reset successfully")
            return jsonify({"status": "ok", "message": f"Game '{game_id}' reset"}), 200
        else:
            return jsonify({"status": "error", "message": "Game format invalid"}), 500

    except Exception as e:
        print(f"🔥 Exception in /reset: {e}")
        return jsonify({"status": "error", "message": f"Internal error: {str(e)}"}), 500


# Update to `app.py`

from flask import Flask, request, jsonify

app = Flask(__name__)

# Store moves as list of strings
games = {}

@app.route("/start", methods=["POST"])
def start_game():
    game_id = request.json.get("game_id")
    device_id = request.json.get("device_id")
    username = request.json.get("username")

    if not game_id or not device_id or not username:
        return jsonify({"status": "error", "message": "Missing game_id, device_id, or username"}), 400

    if game_id in games:
        return jsonify({"status": "error", "message": "Game already exists"}), 400

    games[game_id] = {
        "moves": [],
        "players": [
            {"device_id": device_id, "username": username}
        ]
    }

    return jsonify({
        "status": "ok",
        "message": f"Game '{game_id}' created",
        "players": games[game_id]["players"]
    })


@app.route("/move", methods=["POST"])
def post_move():
    game_id = request.json.get("game_id")
    move = request.json.get("move")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    games[game_id].append(move)
    return jsonify({"status": "ok", "message": f"Move '{move}' recorded"})

@app.route("/lastmove", methods=["GET"])
def get_last_move():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    if not games[game_id]:
        return jsonify({"status": "ok", "move": None})
    return jsonify({"status": "ok", "move": games[game_id][-1]})

# ✅ New: Return full move list
@app.route("/moves", methods=["GET"])
def get_move_list():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    return jsonify({"status": "ok", "moves": games[game_id]})

@app.route("/reset", methods=["POST"])
def reset_game():
    data = request.get_json()
    game_id = data.get("game_id")
    if not game_id:
        return jsonify({"status": "error", "message": "Missing game_id"}), 400
    if game_id in games:
        games[game_id] = []
        return jsonify({"status": "ok", "message": f"Game '{game_id}' reset"})
    return jsonify({"status": "error", "message": f"Game '{game_id}' not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)
