"""
Mud driver (multi user server).

'Tale' mud driver, mudlib and interactive fiction framework
Copyright by Irmen de Jong (irmen@razorvine.net)
"""

import time
import threading
from typing import Union, Generator
from .parseresult import ParseResult
from .story import GameMode
from . import accounts
from . import base
from . import charbuilder
from . import driver
from . import errors
from . import lang
from . import pubsub
from . import races
from . import util
from .player import PlayerConnection, Player
from .tio.mud_browser_io import TaleMudWsgiApp


class MudDriver(driver.Driver):
    """
    The Mud 'driver'.
    Multi-user server variant of the single player Driver.
    """
    def __init__(self, restricted=False) -> None:
        super().__init__()
        self.game_mode = GameMode.MUD
        self.restricted = restricted   # restricted mud mode? (no new players allowed)
        self.mud_accounts = None   # type: accounts.MudAccounts

    def start_mud_webserver(self):
        # Driver runs as main thread, wsgi webserver runs in background thread
        accounts_db_file = self.user_resources.validate_path("useraccounts.sqlite")
        self.mud_accounts = accounts.MudAccounts(accounts_db_file)
        base._limbo.init_inventory([LimboReaper()])  # add the grim reaper to Limbo
        wsgi_server = TaleMudWsgiApp.create_app_server(self)
        wsgi_thread = threading.Thread(name="wsgi", target=wsgi_server.serve_forever)  # type: ignore
        wsgi_thread.daemon = True
        wsgi_thread.start()
        self._print_game_intro(None)
        if self.restricted:
            print("\n* Restricted mode: no new players allowed *\n")
        print("Access the game on this web server url:   http://%s:%d/tale/" % wsgi_server.server_address, end="\n\n")  # type: ignore

    def show_motd(self, player: Player, notify_no_motd: bool=False) -> None:
        """Prints the Message-Of-The-Day file, if present."""
        try:
            message = self.resources["messages/motd.txt"].text.rstrip()
        except IOError:
            message = None
        if message:
            player.tell("<bright>Message-of-the-day:</>", end=True)
            player.tell("\n")
            player.tell(message, end=True, format=True)  # for now, the motd is displayed *with* formatting
            player.tell("\n")
            player.tell("\n")
        elif notify_no_motd:
            player.tell("There's currently no message-of-the-day.", end=True)
            player.tell("\n")

    def do_save(self, player: Player) -> None:
        raise errors.ActionRefused("Currently, saving is not supported in MUD mode.")

    def _connect_player(self, player_io_type: str, line_delay: int) -> PlayerConnection:
        if player_io_type != "web":
            raise ValueError("mud connections can only be done via web interface")
        connection = PlayerConnection()
        connect_name = "<connecting_%d>" % id(connection)  # unique temporary name
        new_player = Player(connect_name, "n", "elemental", "This player is still connecting to the game.")
        connection.player = new_player
        from .tio.mud_browser_io import MudHttpIo
        connection.io = MudHttpIo(connection)
        self.all_players[new_player.name] = connection
        connection.clear_screen()
        self._print_game_intro(connection)
        connection.output("\n")
        # check if we have at least 1 admin user
        if len(self.mud_accounts.all_accounts(having_privilege="wizard")) == 0:
            # there is no wizard, create a dialog to construct the initial admin user
            driver.topic_async_dialogs.send((connection, self._login_dialog_mud_create_admin(connection)))
            return connection
        # create the login dialog
        driver.topic_async_dialogs.send((connection, self._login_dialog_mud(connection)))
        return connection

    def _disconnect_mud_player(self, conn_or_player: Union[PlayerConnection, Player]) -> None:
        # note: conn can be corrupt/disconnected. conn.player, conn.io or conn.player.location can be None.
        if isinstance(conn_or_player, PlayerConnection):
            name = conn_or_player.player.name
            conn = conn_or_player
        elif isinstance(conn_or_player, Player):
            name = conn_or_player.name
            conn = self.all_players[name]
        else:
            raise TypeError("connection or player object expected")
        assert self.all_players[name] is conn
        if conn.player.location:
            conn.player.tell_others("{Title} suddenly shimmers and fades from sight. %s left the game."
                                    % lang.capital(conn.player.subjective))
        del self.all_players[name]
        conn.write_output()
        # wait a bit to allow the player's screen to display the last goodbye message before killing the connection
        self.defer(1, conn.destroy)

    def _login_dialog_mud_create_admin(self, conn: PlayerConnection) -> Generator:
        assert self.story.config.server_mode == GameMode.MUD
        conn.write_output()
        conn.output("<bright>Welcome. There is no admin user registered. "
                    "You'll have to create the initial admin user to be able to start the mud.</>")
        while True:
            conn.output("Creating new admin user.")
            name = yield "input-noecho", ("Please type in the admin's player name.", accounts.MudAccounts.accept_name)
            password = yield "input-noecho", ("Please type in the admin password.", accounts.MudAccounts.accept_password)
            email = yield "input", ("Please type in the admin's email address.", accounts.MudAccounts.accept_email)
            conn.output("You can choose one of the following races: ", lang.join(races.playable_races))
            race = yield "input", ("Player race?", charbuilder.valid_playable_race)
            gender = yield "input", ("What is your gender (m/f/n)?", lang.validate_gender)
            # review the account
            conn.player.tell("<bright>Please review your new character.</>", end=True)
            conn.player.tell("<dim> name:</> %s,  <dim>gender:</> %s,  <dim>race:</> %s,  <dim>email:</> %s" %
                             (name, lang.GENDERS[gender], race, email), end=True)
            if not (yield "input", ("You cannot change your name later. Do you want to create this admin account?", lang.yesno)):
                continue
            else:
                break
        stats = base.Stats.from_race(race, gender=gender[0])
        self.mud_accounts.create(name, password, email, stats, privileges={"wizard"})
        conn.output("\n")
        conn.output("\n")
        yield from self._login_dialog_mud(conn)  # continue with the normal login dialog

    def _login_dialog_mud(self, conn: PlayerConnection) -> Generator:
        assert self.story.config.server_mode == GameMode.MUD
        conn.write_output()
        conn.output("<bright>Welcome. We would like to know your player name before you can continue.</>")
        conn.output("<dim>If you are not yet known with us, you can simply type in a new name. "
                    "Otherwise use the name you registered with.</>\n")
        conn.output("\n")
        while True:
            name = yield "input-noecho", ("Please type in your player name.", accounts.MudAccounts.accept_name)
            existing_player = self.search_player(name)
            if existing_player:
                conn.player.tell("That player is already logged in elsewhere. Their current location is " + existing_player.location.name)
                conn.player.tell("and their idle time is %d seconds." % existing_player.idle_time)
                if existing_player.idle_time < 30:
                    conn.player.tell("They are still active.")
                    continue
                if not (yield "input", ("Do you want to kick them out and take over?", lang.yesno)):
                    conn.player.tell("Okay, leaving them in peace.")
                    continue
            try:
                self.mud_accounts.get(name)
                password = yield "input-noecho", "Please type in your password."
            except KeyError:
                if self.restricted:
                    conn.player.tell("<bright>We're sorry, the mud is running in restricted mode at the moment. "
                                     "It is not allowed to create new characters right now. Please try again later.</bright>")
                    continue
                conn.player.tell("'<player>%s</>' is the name of a new character." % name)
                if not (yield "input", ("Do you want to create a new character with this name?", lang.yesno)):
                    continue
                # self-service account creation
                conn.player.tell("\n")
                builder = charbuilder.MudCharacterBuilder(conn, name)
                result = yield from builder.build_character()
                if not result:
                    continue
                name, password = result.name, result.password
                self.mud_accounts.create(name, password, result.email, result.stats)
                conn.player.tell("\n<bright>Your new account has been created!</>  It will now be used to log in.", end=True)
                conn.player.tell("\n")
            try:
                self.mud_accounts.valid_password(name, password)
            except ValueError as x:
                conn.output("<it>%s</it>" % x)
                continue
            else:
                account = self.mud_accounts.get(name)
                if existing_player:
                    # take the place of already logged in player (that was disconnected perhaps?)
                    existing_player.tell("\n")
                    existing_player.tell("<it><rev>You are kicked from the game. Your account is now logged in from elsewhere.</>")
                    existing_player.tell("\n")
                    state = existing_player.__getstate__()
                    state["name"] = conn.player.name    # we can only take the real name after existing player has been kicked out
                    existing_player_location = existing_player.location
                    self._disconnect_mud_player(existing_player)
                    ctx = util.Context(self, self.game_clock, self.story.config, None)
                    # mr. Smith move: delete the other player and restore its properties in us
                    existing_player.destroy(ctx)
                    conn.player.__setstate__(state)
                    name_info = charbuilder.PlayerNaming()
                    name_info.money = state["money"]
                    name_info.name = state["name"]
                    name_info.gender = state["gender"]
                    name_info.stats = state["stats"]
                    name_info.name = account.name   # assume the real name now
                    self._rename_player(conn.player, name_info)
                    conn.output("\n")
                    same_location = conn.player.location is existing_player_location
                    conn.player.move(existing_player_location, silent=same_location)
                    if same_location:
                        conn.player.location.tell("%s appears again. Is %s a different person, you wonder?" %
                                                  (lang.capital(conn.player.title), conn.player.subjective), exclude_living=conn.player)
                else:
                    # log in normally
                    self.mud_accounts.logged_in(name)
                    if account.logged_in:
                        conn.output("Last login: " + str(account.logged_in))
                break
        if not existing_player:
            # for a new login, we need to rename the transitional player object
            # to the proper account name, and move the player to the starting location.
            name_info = charbuilder.PlayerNaming()
            name_info.name = account.name
            name_info.gender = account.stats.gender
            name_info.stats = account.stats
            self._rename_player(conn.player, name_info)
            conn.player.privileges = account.privileges
            conn.output("\n")
            if "wizard" in conn.player.privileges:
                conn.player.move(self._lookup_location(self.story.config.startlocation_wizard))
            else:
                conn.player.move(self._lookup_location(self.story.config.startlocation_player))
        prompt = self.story.welcome(conn.player)
        if prompt:
            yield "input", "\n" + prompt
        self.story.init_player(conn.player)
        conn.output("\n")
        self.show_motd(conn.player, True)
        conn.player.look(short=False)  # force a 'look' command to get our bearings
        # after this, the generator (dialog) ends and we drop down into the regular command loop

    def _main_loop_multiplayer(self) -> None:
        """
        The game loop, for the multiplayer MUD mode.
        Until the server is shut down, it processes player input, and prints the resulting output.
        """
        loop_duration = 0.0
        previous_server_tick = 0.0
        while not self._stop_mainloop:
            pubsub.sync("driver-async-dialogs")
            for conn in self.all_players.values():
                conn.write_output()
                if conn not in self.waiting_for_input:
                    conn.write_input_prompt()

            # server tick goes on a timer
            wait_time = max(0.01, self.story.config.server_tick_time - loop_duration)
            while wait_time > 0:
                if any(conn.player.input_is_available.is_set() for conn in self.all_players.values()):
                    # there was player input, abort the wait loop and deal with it
                    break
                sub_wait = min(0.1, wait_time)  # keep things responsive
                time.sleep(sub_wait)
                wait_time -= sub_wait

            loop_start = time.time()
            for conn in list(self.all_players.values()):
                if conn.player.input_is_available.is_set():
                    conn.need_new_input_prompt = True
                    try:
                        if conn in self.waiting_for_input:
                            # this connection is processing direct input, rather than regular commands
                            dialog, validator, echo_input = self.waiting_for_input.pop(conn)
                            response = conn.player.get_pending_input()[0]
                            if validator:
                                try:
                                    response = validator(response)
                                except ValueError as x:
                                    prompt = conn.last_output_line
                                    conn.io.dont_echo_next_cmd = not echo_input
                                    conn.output(str(x) or "That is not a valid answer.")
                                    conn.output_no_newline(prompt)   # print the input prompt again
                                    self.waiting_for_input[conn] = (dialog, validator, echo_input)   # reschedule
                                    continue
                            self._continue_dialog(conn, dialog, response)
                        else:
                            # normal command processing
                            self._server_loop_process_player_input(conn)
                    except (KeyboardInterrupt, EOFError):
                        continue
                    except errors.SessionExit:
                        self.story.goodbye(conn.player)
                        driver.topic_pending_tells.send(lambda conn=conn: self._disconnect_mud_player(conn))
                    except Exception:
                        tb = "".join(util.format_traceback())
                        txt = "\n<bright><rev>* internal error (please report this):</>\n" + tb
                        conn.player.tell(txt, format=False)
                        conn.player.tell("<rev><it>Please report this problem.</>")
            pubsub.sync("driver-pending-tells")
            # server TICK
            now = time.time()
            if now - previous_server_tick >= self.story.config.server_tick_time:
                self._server_tick()
                previous_server_tick = now
            loop_duration = time.time() - loop_start
            self.server_loop_durations.append(loop_duration)


class LimboReaper(base.Living):
    """The Grim Reaper hangs about in Limbo, and makes sure no one stays there for too long."""
    def __init__(self) -> None:
        super().__init__(
            "reaper", "m", "elemental", "Grim Reaper",
            description="He wears black robes with a hood. Where a face should be, there is only nothingness. "
                        "He is carrying a large ominous scythe that looks very, very sharp.",
            short_description="A figure clad in black, carrying a scythe, is also present.")
        self.aliases = {"figure", "death"}
        self.candidates = {}    # type: Dict[base.Living, Tuple[float, int]]  # living (usually a player) --> (first_seen, texts shown)

    def notify_action(self, parsed: ParseResult, actor: base.Living) -> None:
        if parsed.verb == "say":
            actor.tell("%s just stares blankly at you, not saying a word." % lang.capital(self.title))
        else:
            actor.tell("%s stares blankly at you." % lang.capital(self.title))

    @util.call_periodically(3)
    def do_reap_souls(self, ctx: util.Context) -> None:
        # consider all livings currently in Limbo or having their location set to Limbo
        if self.location is not base._limbo:
            # we somehow got misplaced, teleport back to limbo
            self.tell_others("{Title} looks around in wonder and says, \"I'm not supposed to be here.\"")
            self.move(base._limbo, self)
            return
        in_limbo = {living for living in self.location.livings if living is not self}
        in_limbo.update({conn.player for conn in ctx.driver.all_players.values() if conn.player.location is base._limbo})
        now = time.time()
        for candidate in in_limbo:
            if candidate not in self.candidates:
                self.candidates[candidate] = (now, 0)   # a new player first seen
        for candidate in list(self.candidates):
            if candidate not in in_limbo:
                del self.candidates[candidate]   # player no longer present in limbo
                continue
            first_seen, shown = self.candidates[candidate]
            duration = now - first_seen
            # Depending on how long the candidate is being observed, show increasingly threateningly warnings,
            # and eventually killing the candidate (and closing their connection).
            # For wizard players, this is not done and only a short notification is printed.
            if "wizard" in candidate.privileges and duration >= 2 and shown < 1:
                candidate.tell(self.title + " whispers: \"Hello there wizard. Please don't stay for too long.\"")
                shown = 99999
            if duration >= 30 and shown < 1:
                candidate.tell(self.title + " whispers: \"Greetings. Be aware that you must not linger here... Decide swiftly...\"")
                shown = 1
            elif duration >= 50 and shown < 2:
                candidate.tell(self.title + " looms over you and warns: \"You really cannot stay here much longer!\"")
                shown = 2
            elif duration >= 60 and shown < 3:
                candidate.tell(self.title + " menacingly raises his scythe!")
                shown = 3
            elif duration >= 63 and shown < 4:
                candidate.tell(self.title + " swings down his scythe and slices your soul cleanly in half. You are destroyed.")
                shown = 4
            elif duration >= 64 and "wizard" not in candidate.privileges:
                try:
                    conn = ctx.driver.all_players[candidate.name]
                except KeyError:
                    pass   # already gone
                else:
                    ctx.driver._disconnect_mud_player(conn)
            self.candidates[candidate] = (first_seen, shown)