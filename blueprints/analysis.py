import chess
from flask import Blueprint, jsonify, request
from stockfish import Stockfish
from core.config import STOCKFISH_PATH
from core.security import rate_limit, validate_fen, validate_uci_move

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analyze_position', methods=['POST'])
@rate_limit(max_requests=30, window_seconds=60)
def analyze_position():
    data = request.get_json(silent=True) or {}
    fen = str(data.get('fen', '')).strip()
    prev_fen = str(data.get('prev_fen', '')).strip()
    played_uci = str(data.get('move', '')).strip().lower()

    if not validate_fen(fen):
        return jsonify({"error": "Posição FEN inválida."}), 400

    try:
        engine = Stockfish(path=STOCKFISH_PATH)
        engine.set_fen_position(fen)
        engine.set_skill_level(20)
        eval_data = engine.get_evaluation()
        best_moves = engine.get_top_moves(1)
        best_move_uci = best_moves[0]['Move'] if best_moves else None

        classification = 'good'
        if prev_fen and validate_fen(prev_fen) and validate_uci_move(played_uci):
            prev_engine = Stockfish(path=STOCKFISH_PATH)
            prev_engine.set_fen_position(prev_fen)
            prev_eval = prev_engine.get_evaluation()

            val_now = eval_data.get('value', 0) if eval_data.get('type') == 'cp' else (1000 if eval_data.get('value', 0) > 0 else -1000)
            val_prev = prev_eval.get('value', 0) if prev_eval.get('type') == 'cp' else (1000 if prev_eval.get('value', 0) > 0 else -1000)

            prev_board = chess.Board(prev_fen)
            turn_mult = 1 if prev_board.turn == chess.WHITE else -1
            cp_diff = (val_prev * turn_mult) - (val_now * turn_mult)

            if played_uci == best_move_uci:
                classification = 'best'
            elif cp_diff <= 15:
                classification = 'best'
            elif cp_diff <= 50:
                classification = 'good'
            elif cp_diff <= 120:
                classification = 'inaccuracy'
            elif cp_diff <= 250:
                classification = 'mistake'
            else:
                classification = 'blunder'

        return jsonify({
            "success": True,
            "eval": eval_data,
            "best_move": best_move_uci,
            "classification": classification
        })
    except Exception as e:
        return jsonify({"error": "Falha na análise da engine."}), 500
