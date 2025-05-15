from flask import Flask, request, jsonify

app = Flask(__name__)

games = {}

@app.route("/start", methods=["POST"])
def start_game():
    game_id = request.json.get("game_id")
    if game_id in games:
        return jsonify({"status": "error", "message": "Game already exists"}), 400
    games[game_id] = []
    return jsonify({"status": "ok", "message": f"Game '{game_id}' created"})

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

if __name__ == "__main__":
    app.run(debug=True)
