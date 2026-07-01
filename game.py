class Game:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.host_id = None
        self.category = None
        self.category_chosen_once = False
        self.word = None
        self.used_words = set()
        self.scores = {}
        self.player_names = {}
        self.rounds = 0
        # After a round is won, only this user may claim the host button next.
        self.pending_winner_id = None

    def remember_player(self, user):
        name = user.full_name or user.first_name or user.username or str(user.id)
        self.player_names[user.id] = name
        return name

    def get_name(self, user_id):
        return self.player_names.get(user_id, f"User {user_id}")

    def scoreboard_text(self):
        if not self.scores:
            return "Hozircha ballar yo'q."
        lines = [
            f"{self.get_name(uid)}: {score}"
            for uid, score in sorted(self.scores.items(), key=lambda x: -x[1])
        ]
        return "🏆 Reyting:\n" + "\n".join(lines)


class GameManager:
    def __init__(self):
        self.games = {}

    def create(self, chat_id):
        game = Game(chat_id)
        self.games[chat_id] = game
        return game

    def get(self, chat_id):
        return self.games.get(chat_id)

    def exists(self, chat_id):
        return chat_id in self.games

    def end(self, chat_id):
        return self.games.pop(chat_id, None)

    def find_hosted_by(self, user_id):
        for chat_id, game in self.games.items():
            if game.host_id == user_id:
                return chat_id
        return None


# One shared instance used across the whole bot (one process = one manager).
manager = GameManager()