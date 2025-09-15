import os
import random
import json
import time
from threading import Thread
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, emit
from dotenv import load_dotenv
from database import get_db_connection, put_db_connection
import uuid

# Load environment variables
load_dotenv()

app = Flask(__name__)
# The SECRET_KEY can be any random string in development, but should be a secure secret in production.
app.config['SECRET_KEY'] = os.getenv("SUPABASE_KEY")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Global state for active games
# Use a class for better encapsulation and to prevent race conditions on state
game_rooms = {}

ROLES = ['VC', 'Professor', 'Invigilator', 'Cheater', 'Student', 'Student']

class GameRoom:
    def __init__(self, room_code, host_sid):
        self.room_code = room_code
        self.players = {}  # key: username, value: {'sid': sid, 'role': None, 'ready': False}
        self.host_sid = host_sid
        self.state = 'lobby'
        self.timer_thread = None

    def add_player(self, username, sid):
        if username not in self.players:
            self.players[username] = {'sid': sid, 'role': None, 'ready': False}
            # Broadcast the updated player list to the lobby
            player_list = list(self.players.keys())
            socketio.emit('update_players', {'players': player_list}, room=self.room_code)
            socketio.emit('message', {'msg': f'{username} has joined.'}, room=self.room_code)
            self.check_ready_status()
            
    def remove_player(self, username):
        if username in self.players:
            del self.players[username]
            socketio.emit('message', {'msg': f'{username} has left.'}, room=self.room_code)
            player_list = list(self.players.keys())
            socketio.emit('update_players', {'players': player_list}, room=self.room_code)
            self.check_ready_status()
    
    def set_ready(self, username):
        if username in self.players:
            self.players[username]['ready'] = True
            self.check_ready_status()
    
    def check_ready_status(self):
        ready_count = sum(1 for p in self.players.values() if p['ready'])
        total_count = len(self.players)
        socketio.emit('ready_status', {'ready': ready_count, 'total': total_count}, room=self.room_code)
        
        # Check if all players are ready and if the host should be enabled to start
        if total_count >= 3 and ready_count == total_count:
            socketio.emit('enable_start_button', room=self.host_sid)

    def start_game(self):
        if self.state == 'lobby' and len(self.players) >= 3:
            self.state = 'in_progress'
            players = list(self.players.keys())
            available_roles = random.sample(ROLES, len(players))

            for player_name, role in zip(players, available_roles):
                self.players[player_name]['role'] = role
                sid = self.players[player_name]['sid']
                socketio.emit('role_reveal', {'role': role}, room=sid)

            # Send player list to Invigilator after roles are assigned
            players_list = list(self.players.keys())
            for player_name, player_data in self.players.items():
                if player_data['role'] == 'Invigilator':
                    other_players = [p for p in players_list if p != player_name]
                    socketio.emit('update_player_options', {'players': other_players}, room=player_data['sid'])

            # Start the timer as a background task using a Thread
            self.timer_thread = Thread(target=self.game_timer, args=(90,))
            self.timer_thread.daemon = True
            self.timer_thread.start()

            return {"status": "success"}
        return {"status": "error", "message": "Not enough players to start."}

    def game_timer(self, duration):
        for i in range(duration, 0, -1):
            if self.state != 'in_progress':
                break
            socketio.emit('timer_update', {'time_left': i}, room=self.room_code)
            time.sleep(1)
        else:
            if self.state == 'in_progress':
                socketio.emit('game_over', {'result': 'Time Khatam! Cheater bach nikla.'}, room=self.room_code)
                self.log_game_result('Cheater', 'escaped')
                self.state = 'finished'

    def make_guess(self, guesser, target):
        if self.state != 'in_progress':
            return

        target_role = self.players.get(target, {}).get('role')
        if target_role == 'Cheater':
            socketio.emit('game_over', {'result': f'Pakda Gaya! {target} hi asli Cheater tha!'}, room=self.room_code)
            self.log_game_result('Invigilator', 'caught')
        else:
            socketio.emit('game_over', {'result': f'Arre Nahi! Invigilator ne ek masoom Student ko pakad liya.'}, room=self.room_code)
            self.log_game_result('Cheater', 'escaped_by_error')
        
        self.state = 'finished'
        if self.timer_thread and self.timer_thread.is_alive():
            self.timer_thread = None # Stop the timer loop

    def log_game_result(self, winner_role, result_type):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
            INSERT INTO game_results (room_code, winner_role, result_type)
            VALUES (%s, %s, %s);
            """
            cursor.execute(query, (self.room_code, winner_role, result_type))
            conn.commit()
            print(f"Game result logged for room {self.room_code}.")
        except Exception as e:
            print(f"Error logging game result: {e}")
        finally:
            if conn:
                put_db_connection(conn)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    room_code = str(uuid.uuid4())[:6].upper()
    game_rooms[room_code] = GameRoom(room_code, None) # The host SID will be set on join
    return jsonify({"room_code": room_code, "link": f"/lobby/{room_code}"})

@app.route('/lobby/<room_code>')
def lobby(room_code):
    if room_code not in game_rooms:
        return redirect(url_for('index'))
    return render_template('lobby.html', room_code=room_code)

@app.route('/game/<room_code>')
def game_screen(room_code):
    if room_code not in game_rooms:
        return redirect(url_for('index'))
    return render_template('game.html', room_code=room_code)

@socketio.on('connect')
def handle_connect():
    print(f"Client connected with SID: {request.sid}")

@socketio.on('join_game')
def handle_join_game(data):
    username = data.get('username')
    room_code = data.get('room_code')
    sid = request.sid
    if not username or not room_code or room_code not in game_rooms:
        return
    
    game = game_rooms[room_code]
    # Set the host SID for the first player to join
    if not game.host_sid:
        game.host_sid = sid
        
    game.add_player(username, sid)
    join_room(room_code)
    
@socketio.on('set_ready')
def handle_set_ready(data):
    username = data.get('username')
    room_code = data.get('room_code')
    if room_code in game_rooms:
        game = game_rooms[room_code]
        game.set_ready(username)

@socketio.on('start_game_request')
def handle_start_game_request(data):
    room_code = data.get('room_code')
    sid = request.sid
    if room_code in game_rooms:
        game = game_rooms[room_code]
        # Security check: only allow the host to start the game
        if sid == game.host_sid:
            game.start_game()
        else:
            emit('message', {'msg': 'Only the host can start the game.'})

@socketio.on('make_guess')
def handle_make_guess(data):
    guesser = data.get('guesser')
    target = data.get('target')
    room_code = data.get('room_code')
    if room_code in game_rooms:
        game = game_rooms[room_code]
        game.make_guess(guesser, target)
    
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for room_code, game in list(game_rooms.items()):
        for player_name, player_data in list(game.players.items()):
            if player_data['sid'] == sid:
                game.remove_player(player_name)
                print(f"Player {player_name} disconnected from room {room_code}.")
                # If the host disconnects, delete the room
                if sid == game.host_sid:
                    print(f"Host disconnected. Deleting room {room_code}.")
                    del game_rooms[room_code]
                return