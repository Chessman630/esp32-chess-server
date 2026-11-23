
import chess
import psycopg


def submit_move(conn, game_id, user_id, uci,
                expected_move_count, request_id):
    """
    Submit one chess move using an atomic PostgreSQL transaction.

    user_id is trusted only for local testing. In production,
    it must come from verified authentication.
    """

    with conn.transaction():
        with conn.cursor() as cur:

            # Lock this game until the transaction completes.
            cur.execute(
                """
                SELECT white_user_id, black_user_id,
                       status, turn
                FROM games
                WHERE game_id = %s
                FOR UPDATE
                """,
                (game_id,),
            )

            game = cur.fetchone()
            if game is None:
                raise ValueError("Game not found")

            white_id, black_id, status, stored_turn = game

            # Check for a previously committed request.
            cur.execute(
                """
                SELECT game_id, user_id, uci, ply_number
                FROM moves
                WHERE request_id = %s
                """,
                (request_id,),
            )

            previous = cur.fetchone()
            if previous is not None:
                old_game, old_user, old_uci, old_ply = previous

                if (
                    str(old_game) != str(game_id)
                    or str(old_user) != str(user_id)
                    or old_uci != uci
                    or old_ply != expected_move_count + 1
                ):
                    raise ValueError("Request ID reused with different data")

                return {
                    "accepted": True,
                    "duplicate": True,
                    "ply": old_ply,
                }

            if status != "active":
                raise ValueError("Game is not active")

            # Retrieve the authoritative move history.
            cur.execute(
                """
                SELECT ply_number, uci
                FROM moves
                WHERE game_id = %s
                ORDER BY ply_number
                """,
                (game_id,),
            )

            history = cur.fetchall()

            board = chess.Board()

            for expected_ply, (ply, previous_uci) in enumerate(
                history, start=1
            ):
                if ply != expected_ply:
                    raise ValueError("Move history contains a gap")

                try:
                    board.push_uci(previous_uci)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid stored move at ply {ply}"
                    ) from exc

            if stored_turn != (
                "white" if board.turn == chess.WHITE else "black"
            ):
                raise ValueError("Stored turn disagrees with move history")

            if expected_move_count != len(history):
                raise ValueError("Move count mismatch; refresh required")

            expected_user = white_id if board.turn else black_id

            if str(expected_user) != str(user_id):
                raise ValueError("Not authorized to move this turn")

            if board.is_game_over(claim_draw=False):
                raise ValueError("Game is already finished")

            try:
                move = chess.Move.from_uci(uci)
            except ValueError as exc:
                raise ValueError("Invalid UCI move") from exc

            if move not in board.legal_moves:
                raise ValueError("Illegal chess move")

            board.push(move)
            next_turn = "white" if board.turn else "black"
            next_ply = len(history) + 1

            # Store the move.
            cur.execute(
                """
                INSERT INTO moves (
                    game_id, ply_number, user_id,
                    uci, request_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (game_id, next_ply, user_id, uci, request_id),
            )

            # Update the game's turn in the same transaction.
            cur.execute(
                """
                UPDATE games
                SET turn = %s
                WHERE game_id = %s
                """,
                (next_turn, game_id),
            )

            if cur.rowcount != 1:
                raise RuntimeError("Failed to update game turn")

            return {
                "accepted": True,
                "duplicate": False,
                "ply": next_ply,
                "next_turn": next_turn,
            }
