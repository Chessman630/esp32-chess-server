
-- ESP32 Chess Server
-- Initial PostgreSQL development schema

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS games (
    game_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_name VARCHAR(64) NOT NULL,

    creator_id UUID NOT NULL REFERENCES users(user_id),
    white_user_id UUID REFERENCES users(user_id),
    black_user_id UUID REFERENCES users(user_id),

    status VARCHAR(20) NOT NULL DEFAULT 'waiting',
    turn VARCHAR(5),

    result VARCHAR(10),
    end_reason VARCHAR(40),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_game_status
        CHECK (status IN ('waiting', 'active', 'paused', 'completed')),

    CONSTRAINT valid_turn
        CHECK (turn IN ('white', 'black') OR turn IS NULL),

    CONSTRAINT different_players
        CHECK (
            white_user_id IS NULL OR
            black_user_id IS NULL OR
            white_user_id <> black_user_id
        )
);

CREATE TABLE IF NOT EXISTS moves (
    move_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    game_id UUID NOT NULL REFERENCES games(game_id)
        ON DELETE CASCADE,

    ply_number INTEGER NOT NULL CHECK (ply_number > 0),

    user_id UUID NOT NULL REFERENCES users(user_id),

    uci VARCHAR(5) NOT NULL,

    request_id UUID NOT NULL,

    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_game_ply
        UNIQUE (game_id, ply_number),

    CONSTRAINT unique_move_request
        UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_games_creator
    ON games(creator_id);

CREATE INDEX IF NOT EXISTS idx_moves_game
    ON moves(game_id, ply_number);
