from flask import Flask, request, jsonify

app = Flask(__name__)
games = {}

@app.route("/start", methods=["POST"])
def start_game():
    game_id = request.json.get("game_id")
    if game_id in games:
        return jsonify({"status": "error", "message": "Game already exists"}), 400
    games[game_id] = {"moves": []}  # ✅ store as dict with "moves" list
    return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

@app.route("/move", methods=["POST"])
def post_move():
    game_id = request.json.get("game_id")
    move = request.json.get("move")
    if game_id not in games:
        return jsonify({"status": "error", "message": "Game not found"}), 404
    games[game_id]["moves"].append(move)  # ✅ access "moves" key
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
    data = request.get_json()
    print("🔧 /reset called with data:", data)

    game_id = data.get("game_id")
    if not game_id:
        return jsonify({"status": "error", "message": "Missing game_id"}), 400

    if game_id in games:
        print(f"✅ Resetting game: {game_id}")
        games[game_id]["moves"] = []  # ✅ valid now
        return jsonify({"status": "ok", "message": f"Game '{game_id}' reset"}), 200
    else:
        print(f"⚠️ Game not found: {game_id}")
        return jsonify({"status": "error", "message": f"Game '{game_id}' not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)

