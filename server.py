from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

games = {}

@app.route("/start", methods=["POST"])
def start_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")
    username = data.get("username")
    pin = data.get("pin")
    is_open = data.get("open", False)

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        games[game_id] = {
            "owners": [device_id],
            "usernames": [username or ""],
            "moves": [],
            "open": is_open,
            "pin": pin if pin else None
        }
        return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

    game = games[game_id]
    if device_id in game["owners"]:
        return jsonify({"status": "ok", "message": "Rejoined your own game"})

    if len(game["owners"]) >= 2:
        return jsonify({"status": "error", "message": "Game already has two players"}), 403

    if game.get("pin") and pin != game["pin"]:
        return jsonify({"status": "error", "message": "Incorrect or missing invitation PIN"}), 403

    game["owners"].append(device_id)
    game["usernames"].append(username or "")
    game["open"] = False
    return jsonify({"status": "ok", "message": "Joined as second player"})


@app.route("/join", methods=["POST"])
def join_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")
    username = data.get("username")
    pin = data.get("pin")

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    game = games[game_id]
    if device_id in game["owners"]:
        return jsonify({"status": "ok", "message": "Rejoined your own game"})

    if len(game["owners"]) >= 2:
        return jsonify({"status": "error", "message": "Game already has two players"}), 403

    if game.get("pin") and pin != game["pin"]:
        return jsonify({"status": "error", "message": "Incorrect or missing invitation PIN"}), 403

    game["owners"].append(device_id)
    game["usernames"].append(username or "")
    game["open"] = False
    return jsonify({"status": "ok", "message": f"Joined game '{game_id}' as second player"})


@app.route("/games/open", methods=["GET"])
def list_open_games():
    open_games = []
    for game_id, game in games.items():
        if game.get("open", False) and len(game.get("owners", [])) == 1:
            open_games.append({
                "game_id": game_id,
                "username": game.get("usernames", [""])[0]
            })
    return jsonify({"status": "ok", "open_games": open_games})


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
    if device_id not in game.get("owners", []):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    game["moves"].append(move)
    print(f"🎮 Game '{game_id}' moves: {game['moves']}")
    return jsonify({"status": "ok", "message": f"Move '{move}' recorded"})


@app.route("/lastmove", methods=["GET"])
def get_last_move():
    game_id = request.args.get("game_id")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    moves = games[game_id].get("moves", [])
    return jsonify({"status": "ok", "move": moves[-1] if moves else None})


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
    if device_id not in game.get("owners", []):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    game["moves"] = []
    print(f"🔄 Game '{game_id}' reset by {device_id}")
    return jsonify({"status": "ok", "message": f"Game '{game_id}' reset"})


@app.route("/delete", methods=["POST"])
def delete_game():
    data = request.get_json()
    game_id = data.get("game_id")
    device_id = data.get("device_id")

    if not game_id or not device_id:
        return jsonify({"status": "error", "message": "Missing game_id or device_id"}), 400

    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404

    if device_id not in games[game_id].get("owners", []):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    del games[game_id]
    print(f"❌ Game '{game_id}' deleted by {device_id}")
    return jsonify({"status": "ok", "message": f"Game '{game_id}' deleted"})


if __name__ == "__main__":
    app.run(debug=True)
 
