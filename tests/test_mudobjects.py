"""
Unittests for Mud base objects

'Tale' mud driver, mudlib and interactive fiction framework
Copyright by Irmen de Jong (irmen@razorvine.net)
"""

import unittest
import datetime
from tests.supportstuff import TestDriver, MsgTraceNPC, Wiretap
from tale.base import Location, Exit, Item, MudObject, Living, _limbo, Container, Weapon, Door, Key, clone
from tale.util import Context, MoneyFormatter
from tale.errors import ActionRefused, LocationIntegrityError
from tale.player import Player
from tale.parseresult import ParseResult
from tale.story import MoneyType
from tale.tio.iobase import strip_text_styles
from tale import pubsub, mud_context
from tale.demo.story import Story as DemoStory


class TestLocations(unittest.TestCase):
    def setUp(self):
        mud_context.driver = TestDriver()
        mud_context.config = DemoStory().config
        self.hall = Location("Main hall", "A very large hall.")
        self.attic = Location("Attic", "A dark attic.")
        self.street = Location("Street", "An endless street.")
        e1 = Exit("up", self.attic, "A ladder leads up.")
        e2 = Exit(["door", "east"], self.street, "A heavy wooden door to the east blocks the noises from the street outside.")
        self.hall.add_exits([e1, e2])
        self.table = Item("table", "oak table", "a large dark table with a lot of cracks in its surface")
        self.key = Item("key", "rusty key", "an old rusty key without a label", short_description="Someone forgot a key.")
        self.magazine = Item("magazine", "university magazine")
        self.magazine2 = Item("magazine", "university magazine")
        self.rat = Living("rat", "n", race="rodent")
        self.rat2 = Living("rat", "n", race="rodent")
        self.fly = Living("fly", "n", race="insect", short_description="A fly buzzes around your head.")
        self.julie = Living("julie", "f", title="attractive Julie", description="She's quite the looker.")
        self.julie.aliases = {"chick"}
        self.player = Player("player", "m")
        self.pencil = Item("pencil", title="fountain pen")
        self.pencil.aliases = {"pen"}
        self.bag = Container("bag")
        self.notebook_in_bag = Item("notebook")
        self.bag.insert(self.notebook_in_bag, self.player)
        self.player.insert(self.pencil, self.player)
        self.player.insert(self.bag, self.player)
        self.hall.init_inventory([self.table, self.key, self.magazine, self.magazine2, self.rat, self.rat2, self.julie, self.player, self.fly])

    def test_names(self):
        loc = Location("The Attic", "A dusty attic.")
        self.assertEqual("The Attic", loc.name)
        self.assertEqual("A dusty attic.", loc.description)

    def test_contains(self):
        self.assertTrue(self.julie in self.hall)
        self.assertTrue(self.magazine in self.hall)
        self.assertFalse(self.pencil in self.hall)
        self.assertFalse(self.magazine in self.attic)
        self.assertFalse(self.julie in self.attic)

    def test_look(self):
        expected = ["[Main hall]", "A very large hall.",
                    "A heavy wooden door to the east blocks the noises from the street outside. A ladder leads up.",
                    "Someone forgot a key. You see two university magazines and an oak table. Player, attractive Julie, and two rats are here. A fly buzzes around your head."]
        self.assertEqual(expected, strip_text_styles(self.hall.look()))
        expected = ["[Main hall]", "A very large hall.",
                    "A heavy wooden door to the east blocks the noises from the street outside. A ladder leads up.",
                    "Someone forgot a key. You see two university magazines and an oak table. Attractive Julie and two rats are here. A fly buzzes around your head."]
        self.assertEqual(expected, strip_text_styles(self.hall.look(exclude_living=self.player)))
        expected = ["[Attic]", "A dark attic."]
        self.assertEqual(expected, strip_text_styles(self.attic.look()))

    def test_look_short(self):
        expected = ["[Attic]"]
        self.assertEqual(expected, strip_text_styles(self.attic.look(short=True)))
        expected = ["[Main hall]", "Exits: door, east, up", "You see: key, two magazines, and table", "Present: fly, julie, player, and two rats"]
        self.assertEqual(expected, strip_text_styles(self.hall.look(short=True)))
        expected = ["[Main hall]", "Exits: door, east, up", "You see: key, two magazines, and table", "Present: fly, julie, and two rats"]
        self.assertEqual(expected, strip_text_styles(self.hall.look(exclude_living=self.player, short=True)))

    def test_search_living(self):
        self.assertEqual(None, self.hall.search_living("<notexisting>"))
        self.assertEqual(None, self.attic.search_living("<notexisting>"))
        self.assertEqual(self.fly, self.hall.search_living("fly"))
        self.assertEqual(self.julie, self.hall.search_living("Julie"))
        self.assertEqual(self.julie, self.hall.search_living("attractive julie"))
        self.assertEqual(self.julie, self.hall.search_living("chick"))
        self.assertEqual(None, self.hall.search_living("bloke"))

    def test_search_item(self):
        # almost identical to locate_item so only do a few basic tests
        self.assertEqual(None, self.player.search_item("<notexisting>"))
        self.assertEqual(self.pencil, self.player.search_item("pencil"))

    def test_locate_item(self):
        item, container = self.player.locate_item("<notexisting>")
        self.assertEqual(None, item)
        self.assertEqual(None, container)
        item, container = self.player.locate_item("pencil")
        self.assertEqual(self.pencil, item)
        self.assertEqual(self.player, container)
        item, container = self.player.locate_item("fountain pen")
        self.assertEqual(self.pencil, item, "need to find the title")
        item, container = self.player.locate_item("pen")
        self.assertEqual(self.pencil, item, "need to find the alias")
        item, container = self.player.locate_item("pencil", include_inventory=False)
        self.assertEqual(None, item)
        self.assertEqual(None, container)
        item, container = self.player.locate_item("key")
        self.assertEqual(self.key, item)
        self.assertEqual(self.hall, container)
        item, container = self.player.locate_item("key", include_location=False)
        self.assertEqual(None, item)
        self.assertEqual(None, container)
        item, container = self.player.locate_item("KEY")
        self.assertEqual(self.key, item, "should work case-insensitive")
        self.assertEqual(self.hall, container, "should work case-insensitive")
        item, container = self.player.locate_item("notebook")
        self.assertEqual(self.notebook_in_bag, item)
        self.assertEqual(self.bag, container, "should search in bags in inventory")
        item, container = self.player.locate_item("notebook", include_containers_in_inventory=False)
        self.assertEqual(None, item)
        self.assertEqual(None, container, "should not search in bags in inventory")

    def test_tell(self):
        rat = MsgTraceNPC("rat", "n", "rodent")
        self.assertTrue(rat._init_called, "init() must be called from __init__")
        julie = MsgTraceNPC("julie", "f", "human")
        hall = Location("hall")
        hall.livings = [rat, julie]
        hall.tell("roommsg")
        self.assertEqual(["roommsg"], rat.messages)
        self.assertEqual(["roommsg"], julie.messages)
        rat.clearmessages()
        julie.clearmessages()
        hall.tell("roommsg", rat, [julie], "juliemsg")
        self.assertEqual([], rat.messages)
        self.assertEqual(["juliemsg"], julie.messages)

    def test_message_nearby_location(self):
        plaza = Location("plaza")
        road = Location("road")
        house = Location("house")
        attic = Location("attic")
        plaza.add_exits([Exit("north", road, "road leads north"), Exit("door", house, "door to a house")])
        road.add_exits([Exit("south", plaza, "plaza to the south")])
        house.add_exits([Exit("door", plaza, "door to the plaza"), Exit("ladder", attic, "dusty attic")])
        attic.add_exits([Exit("ladder", house, "the house")])
        wiretap_plaza = Wiretap(plaza)
        wiretap_road = Wiretap(road)
        wiretap_house = Wiretap(house)
        wiretap_attic = Wiretap(attic)
        plaza.message_nearby_locations("boing")
        pubsub.sync()
        self.assertEqual([], wiretap_plaza.msgs, "the plaza doesnt receive tells")
        self.assertEqual([], wiretap_attic.msgs, "the attic is too far away to receive msgs")
        self.assertTrue(("road", "boing") in wiretap_road.msgs)
        self.assertTrue(("road", "The sound is coming from the south.") in wiretap_road.msgs, "road should give sound direction")
        self.assertTrue(("house", "boing") in wiretap_house.msgs)
        self.assertTrue(("house", "You can't hear where the sound is coming from.") in wiretap_house.msgs, "in the house you can't locate the sound direction")

    def test_nearby(self):
        plaza = Location("plaza")
        road = Location("road")
        house = Location("house")
        alley = Location("alley")  # no exits
        attic = Location("attic")
        plaza.add_exits([Exit("north", road, "road leads north"), Exit("door", house, "door to a house"),
                         Exit("west", alley, "small alleywith no way back")])
        road.add_exits([Exit("south", plaza, "plaza to the south")])
        house.add_exits([Exit("door", plaza, "door to the plaza"), Exit("ladder", attic, "dusty attic")])
        attic.add_exits([Exit("ladder", house, "the house")])
        adj = set(plaza.nearby())
        self.assertSetEqual({road, house}, adj)
        adj = set(plaza.nearby(no_traps=False))
        self.assertSetEqual({road, house, alley}, adj)

    def test_verbs(self):
        room = Location("room")
        room.verbs["smurf"] = ""
        self.assertTrue("smurf" in room.verbs)
        del room.verbs["smurf"]
        self.assertFalse("smurf" in room.verbs)

    def test_enter_leave(self):
        hall = Location("hall")
        rat1 = Living("rat1", "n")
        rat2 = Living("rat2", "n")
        julie = Living("julie", "f")
        with self.assertRaises(TypeError):
            hall.insert(12345, julie)
        self.assertEqual(_limbo, rat1.location)
        self.assertFalse(rat1 in hall.livings)
        wiretap = Wiretap(hall)
        hall.insert(rat1, julie)
        self.assertEqual(hall, rat1.location)
        self.assertTrue(rat1 in hall.livings)
        self.assertEqual([], wiretap.msgs, "insert shouldn't produce arrival messages")
        hall.insert(rat2, julie)
        self.assertTrue(rat2 in hall.livings)
        self.assertEqual([], wiretap.msgs, "insert shouldn't produce arrival messages")
        # now test leave
        wiretap.clear()
        hall.remove(rat1, julie)
        self.assertFalse(rat1 in hall.livings)
        self.assertIsNone(rat1.location)
        self.assertEqual([], wiretap.msgs, "remove shouldn't produce exit message")
        hall.remove(rat2, julie)
        self.assertFalse(rat2 in hall.livings)
        self.assertEqual([], wiretap.msgs, "remove shouldn't produce exit message")
        # test random leave
        hall.remove(rat1, julie)
        hall.remove(12345, julie)

    def test_custom_verbs(self):
        player = Player("julie", "f")
        player.verbs["xywobble"] = "p1"
        monster = Living("snake", "f")
        monster.verbs["snakeverb"] = "s1"
        room = Location("room")
        chair1 = Item("chair1")
        chair1.verbs["frobnitz"] = "c1"
        chair2 = Item("chair2")
        chair2.verbs["frobnitz"] = "c2"
        chair_in_inventory = Item("chair3")
        chair_in_inventory.verbs["kowabooga"] = "c3"
        box_in_inventory = Item("box")
        box_in_inventory.verbs["boxverb"] = "c4"
        player.init_inventory([box_in_inventory, chair_in_inventory])
        exit = Exit("e", "dummy", None, None)
        exit.verbs["exitverb"] = "c5"
        room.init_inventory([chair1, player, chair2, monster])
        room.add_exits([exit])
        custom_verbs = mud_context.driver.current_custom_verbs(player)
        all_verbs = mud_context.driver.current_verbs(player)
        self.assertEqual({"xywobble", "snakeverb", "frobnitz", "kowabooga", "boxverb", "exitverb"}, set(custom_verbs))
        self.assertEqual(set(), set(custom_verbs) - set(all_verbs))

    def test_notify(self):
        room = Location("room")
        room2 = Location("room2")
        player = Player("julie", "f")
        room.notify_player_arrived(player, room2)
        room.notify_player_left(player, room2)
        room.notify_npc_arrived(player, room2)
        room.notify_npc_left(player, room2)
        parsed = ParseResult("verb")
        room.notify_action(parsed, player)


class TestDoorsExits(unittest.TestCase):
    def setUp(self):
        mud_context.driver = TestDriver()
        mud_context.config = DemoStory().config

    def test_state(self):
        Door("out", "xyz", "short desc", locked=False, opened=False)
        Door("out", "xyz", "short desc", locked=False, opened=True)
        Door("out", "xyz", "short desc", locked=True, opened=False)
        with self.assertRaises(ValueError):
            Door("out", "xyz", "short desc", locked=True, opened=True)

    def test_actions(self):
        player = Player("julie", "f")
        hall = Location("hall")
        attic = Location("attic")
        unbound_exit = Exit("random", "foo.bar", "a random exit")
        with self.assertRaises(Exception):
            self.assertFalse(unbound_exit.allow_passage(player))  # should fail because not bound
        exit1 = Exit("ladder", attic, "first ladder to attic")
        exit1.allow_passage(player)

        door = Door("north", hall, "open unlocked door", locked=False, opened=True)
        with self.assertRaises(ActionRefused) as x:
            door.open(player)  # fail, it's already open
        self.assertEqual("It's already open.", str(x.exception))
        door.close(player)
        self.assertFalse(door.opened, "must be closed")
        with self.assertRaises(ActionRefused) as x:
            door.lock(player)  # default door can't be locked
        self.assertEqual("You don't seem to have the means to lock it.", str(x.exception))
        with self.assertRaises(ActionRefused) as x:
            door.unlock(player)  # fail, it's not locked
        self.assertEqual("It's not locked.", str(x.exception))

        door = Door("north", hall, "open locked door", locked=False, opened=True)
        with self.assertRaises(ActionRefused) as x:
            door.open(player)  # fail, it's already open
        self.assertEqual("It's already open.", str(x.exception))
        door.close(player)
        door.locked = True
        with self.assertRaises(ActionRefused) as x:
            door.lock(player)  # it's already locked
        self.assertEqual("It's already locked.", str(x.exception))
        self.assertTrue(door.locked)
        with self.assertRaises(ActionRefused) as x:
            door.unlock(player)  # you can't unlock it
        self.assertEqual("You don't seem to have the means to unlock it.", str(x.exception))
        self.assertTrue(door.locked)

        door = Door("north", hall, "closed unlocked door", locked=False, opened=False)
        door.open(player)
        self.assertTrue(door.opened)
        door.close(player)
        self.assertFalse(door.opened)
        with self.assertRaises(ActionRefused) as x:
            door.close(player)  # it's already closed
        self.assertEqual("It's already closed.", str(x.exception))

        door = Door("north", hall, "closed locked door", locked=True, opened=False)
        with self.assertRaises(ActionRefused) as x:
            door.open(player)  # can't open it, it's locked
        self.assertEqual("You try to open it, but it's locked.", str(x.exception))
        with self.assertRaises(ActionRefused) as x:
            door.close(player)  # it's already closed
        self.assertEqual("It's already closed.", str(x.exception))

        door = Door("north", hall, "Some door.")
        self.assertEqual("Some door.", door.short_description)
        self.assertEqual("Some door. It is open and unlocked.", door.description)
        self.assertTrue(door.opened)
        self.assertFalse(door.locked)
        door = Door("north", hall, "Some door.", "This is a peculiar door leading north.")
        self.assertEqual("Some door.", door.short_description)
        self.assertEqual("This is a peculiar door leading north. It is open and unlocked.", door.description)

    def test_with_key(self):
        player = Player("julie", "f")
        key = Key("key", "door key")
        key.key_for(code=12345)
        hall = Location("hall")
        door = Door("north", hall, "a locked door", locked=True, opened=False)
        door2 = Door("south", hall, "another locked door", locked=True, opened=False)
        with self.assertRaises(ActionRefused):
            door.unlock(player)
        with self.assertRaises(ActionRefused):
            door.unlock(player, key)
        door.key_code = 12345
        door2.key_code = 9999
        key.key_for(door)
        self.assertTrue(door.locked)
        door.unlock(player, key)
        self.assertFalse(door.locked)
        with self.assertRaises(ActionRefused):
            door2.unlock(key)
        door.locked = True
        with self.assertRaises(ActionRefused):
            door.unlock(player)
        key.move(player, player)
        door.unlock(player)
        self.assertFalse(door.locked)
        door.lock(player)
        self.assertTrue(door.locked)
        door.unlock(player)
        player.remove(key, player)
        with self.assertRaises(ActionRefused):
            door.lock(player)
        door.key_code = None
        with self.assertRaises(LocationIntegrityError):
            key.key_for(door)

    def test_exits(self):
        hall = Location("hall")
        attic = Location("attic")
        exit1 = Exit("ladder1", attic, "The first ladder leads to the attic.")
        exit2 = Exit("up", attic, "Second ladder to attic.")
        exit3 = Exit("ladder3", attic, "Third ladder to attic.")
        exit4 = Exit("window", attic, "A window.", "A window, maybe if you open it you can get out?")
        hall.add_exits([exit1, exit2, exit3, exit4])
        self.assertTrue(hall.exits["up"] is exit2)
        self.assertTrue(hall.exits["ladder3"] is exit3)
        self.assertTrue(hall.exits["window"] is exit4)
        self.assertEqual(['[hall]', 'The first ladder leads to the attic. Third ladder to attic. Second ladder to attic. A window.'], strip_text_styles(hall.look()))
        self.assertEqual("Third ladder to attic.", exit3.description)
        self.assertEqual("A window, maybe if you open it you can get out?", exit4.description)
        with self.assertRaises(ActionRefused):
            exit1.activate(None)
        with self.assertRaises(ActionRefused):
            exit1.deactivate(None)
        with self.assertRaises(ActionRefused):
            exit1.close(None, None)
        with self.assertRaises(ActionRefused):
            exit1.open(None, None)
        with self.assertRaises(ActionRefused):
            exit1.lock(None, None)
        with self.assertRaises(ActionRefused):
            exit1.unlock(None, None)
        with self.assertRaises(ActionRefused):
            exit1.manipulate("frobnitz", None)
        with self.assertRaises(ActionRefused):
            exit1.read(None)

    def test_bind_exit(self):
        class ModuleDummy:
            pass
        zones = ModuleDummy()
        zones.town = ModuleDummy()
        zones.town.square = Location("square")
        exit = Exit("square", "town.square", "someplace")
        self.assertIsNone(exit.target)
        self.assertEqual("town.square", exit._target_str)
        exit._bind_target(zones)
        self.assertIsNotNone(exit.target)
        self.assertFalse(hasattr(exit, "_target_str"))
        self.assertTrue(zones.town.square is exit.target)
        exit._bind_target(zones)

    def test_bind_door(self):
        class ModuleDummy:
            pass
        zones = ModuleDummy()
        zones.town = ModuleDummy()
        zones.town.square = Location("square")
        door = Door("square", "town.square", "somewhere")
        self.assertIsNone(door.target)
        self.assertEqual("town.square", door._target_str)
        door._bind_target(zones)
        self.assertIsNotNone(door.target)
        self.assertFalse(hasattr(door, "_target_str"))
        self.assertTrue(zones.town.square is door.target)
        door._bind_target(zones)

    def test_title_name(self):
        door = Door("north", "hall", "a locked door", locked=True, opened=False)
        self.assertEqual("north", door.name)
        self.assertEqual("Exit to <unbound:hall>", door.title)
        exit = Exit("outside", "town.square", "someplace")
        self.assertEqual("outside", exit.name)
        self.assertEqual("Exit to <unbound:town.square>", exit.title)

        class ModuleDummy:
            pass

        zones = ModuleDummy()
        zones.town = ModuleDummy()
        zones.town.square = Location("square")
        exit._bind_target(zones)
        self.assertEqual("Exit to square", exit.title)
        self.assertEqual("exit to square", exit.name)

    def test_aliases(self):
        loc = Location("hall", "empty hall")
        exit = Exit("up", "attic", "ladder to attic")
        door = Door("door", "street", "door to street")
        exit2 = Exit(["down", "hatch", "manhole"], "underground", "hatch to underground")
        door2 = Door(["east", "garden"], "garden", "door east to garden")
        self.assertEqual("up", exit.name)
        self.assertEqual("door", door.name)
        loc.add_exits([exit, door, exit2, door2])
        self.assertEqual({"up", "door", "down", "hatch", "manhole", "east", "garden"}, set(loc.exits.keys()))
        self.assertEqual(loc.exits["down"], loc.exits["hatch"])

    def test_door_pair(self):
        loc1 = Location("room1", "room one")
        loc2 = Location("room2", "room two")
        key = Key("key")
        door_one_two = Door("two", loc2, "door to room two", locked=True, opened=False)
        door_two_one = door_one_two.reverse_door("one", loc1, "door to room one", reverse_open_msg="door one open", reverse_close_msg="door one close",
                                                 this_open_msg="door two open", this_close_msg="door two close")
        loc1.add_exits([door_one_two])
        loc2.add_exits([door_two_one])
        door_one_two.key_code = 555
        key.key_for(door_one_two)
        pubsub1 = PubsubCollector()
        pubsub2 = PubsubCollector()
        loc1.get_wiretap().subscribe(pubsub1)
        loc2.get_wiretap().subscribe(pubsub2)
        self.assertTrue(door_two_one.locked)
        self.assertFalse(door_two_one.opened)
        lucy = Living("lucy", "f")

        door_two_one.unlock(lucy, item=key)
        self.assertFalse(door_one_two.locked)
        door_two_one.open(lucy)
        self.assertTrue(door_one_two.opened)
        pubsub.sync()
        self.assertEqual(["door one open"], pubsub1.messages)
        self.assertEqual([], pubsub2.messages)
        door_one_two.close(lucy)
        door_one_two.lock(lucy, item=key)
        self.assertTrue(door_two_one.locked)
        self.assertFalse(door_two_one.opened)
        pubsub1.clear()
        pubsub2.clear()
        pubsub.sync()
        self.assertEqual([], pubsub1.messages)
        self.assertEqual(["door two close"], pubsub2.messages)


class PubsubCollector(pubsub.Listener):
    def __init__(self):
        self.messages = []

    def pubsub_event(self, topicname, event):
        name, message = event
        self.messages.append(message)

    def clear(self):
        self.messages = []


class TestLiving(unittest.TestCase):
    def test_nocreateliving(self):
        with self.assertRaises(TypeError):
            Living("name")

    def test_lifecycle(self):
        orc = Living("orc", "m", race="orc")
        axe = Weapon("axe")
        orc.insert(axe, orc)
        self.assertIsNotNone(orc.soul)
        self.assertIsNotNone(orc.location)
        self.assertGreater(orc.inventory_size, 0)
        orc.destroy(Context(TestDriver(), None, None, None))
        self.assertIsNone(orc.soul)
        self.assertIsNone(orc.location)
        self.assertEqual(orc.inventory_size, 0)

    def test_contains(self):
        orc = Living("orc", "m", race="orc")
        axe = Weapon("axe")
        orc.insert(axe, orc)
        self.assertTrue(axe in orc)
        self.assertTrue(axe in orc.inventory)
        self.assertEqual(1, orc.inventory_size)
        self.assertEqual(1, len(orc.inventory))

    def test_allowance(self):
        orc = Living("orc", "m", race="half-orc")
        axe = Weapon("axe")
        orc.insert(axe, orc)
        self.assertTrue(axe in orc)
        with self.assertRaises(ActionRefused) as x:
            orc.remove(axe, None)
        self.assertTrue("can't take" in str(x.exception))
        orc.remove(axe, orc)
        self.assertFalse(axe in orc)

    def test_nonitem_insert_fail(self):
        something = Location("thing that is not an Item")
        orc = Living("orc", "m", race="half-orc")
        with self.assertRaises(ActionRefused):
            orc.insert(something, orc)

    def test_move(self):
        hall = Location("hall")
        attic = Location("attic")
        rat = Living("rat", "n", race="rodent")
        hall.init_inventory([rat])
        wiretap_hall = Wiretap(hall)
        wiretap_attic = Wiretap(attic)
        self.assertTrue(rat in hall.livings)
        self.assertFalse(rat in attic.livings)
        self.assertEqual(hall, rat.location)
        rat.move(attic)
        self.assertTrue(rat in attic.livings)
        self.assertFalse(rat in hall.livings)
        self.assertEqual(attic, rat.location)
        pubsub.sync()
        self.assertEqual([("hall", "Rat leaves.")], wiretap_hall.msgs)
        self.assertEqual([("attic", "Rat arrives.")], wiretap_attic.msgs)
        # now try silent
        wiretap_hall.clear()
        wiretap_attic.clear()
        rat.move(hall, silent=True)
        pubsub.sync()
        self.assertTrue(rat in hall.livings)
        self.assertFalse(rat in attic.livings)
        self.assertEqual(hall, rat.location)
        self.assertEqual([], wiretap_hall.msgs)
        self.assertEqual([], wiretap_attic.msgs)

    def test_lang(self):
        living = Living("julie", "f", race="human")
        self.assertEqual("her", living.objective)
        self.assertEqual("her", living.possessive)
        self.assertEqual("she", living.subjective)
        self.assertEqual("f", living.gender)
        living = Living("max", "m", race="human")
        self.assertEqual("him", living.objective)
        self.assertEqual("his", living.possessive)
        self.assertEqual("he", living.subjective)
        self.assertEqual("m", living.gender)
        living = Living("herp", "n", race="human")
        self.assertEqual("it", living.objective)
        self.assertEqual("its", living.possessive)
        self.assertEqual("it", living.subjective)
        self.assertEqual("n", living.gender)

    def test_tell(self):
        julie = Living("julie", "f", race="human")
        tap = julie.get_wiretap()
        collector = PubsubCollector()
        tap.subscribe(collector)
        julie.tell("msg1", "msg2")
        julie.tell("msg3", "msg4", ignored_arg=42)
        pubsub.sync()
        self.assertEqual(["msg1 msg2", "msg3 msg4"], collector.messages)

    def test_show_inventory(self):
        class Ctx:
            class Config:
                pass
            config = Config()

        class MoneyDriverDummy:
            pass

        ctx = Ctx()
        ctx.config.money_type = MoneyType.MODERN
        ctx.driver = MoneyDriverDummy()
        ctx.driver.moneyfmt = MoneyFormatter(ctx.config.money_type)
        julie = Living("julie", "f", race="human")
        tap = julie.get_wiretap()
        collector = PubsubCollector()
        tap.subscribe(collector)
        item1 = Item("key")
        julie.init_inventory([item1])
        julie.money = 9.23
        julie.show_inventory(julie, ctx)
        pubsub.sync()
        text = " ".join(msg.strip() for msg in collector.messages)
        self.assertEqual("Julie is carrying: key Money in possession: 9 dollars and 23 cents.", text)
        ctx.config.money_type = MoneyType.NOTHING
        ctx.driver.moneyfmt = None
        collector.clear()
        julie.show_inventory(julie, ctx)
        pubsub.sync()
        text = " ".join(msg.strip() for msg in collector.messages)
        self.assertEqual("Julie is carrying: key", text)


class TestNPC(unittest.TestCase):
    def test_init(self):
        rat = Living("rat", "n", race="rodent")
        julie = Living("julie", "f", title="attractive Julie",
                    description="""
                    She's quite the looker.
                    """, race="human")
        self.assertFalse(julie.aggressive)
        self.assertEqual("julie", julie.name)
        self.assertEqual("attractive Julie", julie.title)
        self.assertEqual("She's quite the looker.", julie.description)
        self.assertEqual("human", julie.stats.race)
        self.assertEqual("f", julie.gender)
        self.assertTrue(1 < julie.stats.agi < 100)
        self.assertEqual("rat", rat.name)
        self.assertEqual("rat", rat.title)
        self.assertEqual("rodent", rat.stats.race)
        self.assertEqual("", rat.description)
        self.assertEqual("n", rat.gender)
        self.assertTrue(1 < rat.stats.agi < 100)
        dragon = Living("dragon", "f", race="dragon")
        self.assertFalse(dragon.aggressive)

    def test_init_inventory(self):
        rat = Living("rat", "n", race="rodent")
        with self.assertRaises(ActionRefused):
            rat.insert(Item("thing"), None)
        rat.insert(Item("thing"), rat)
        wizz = Player("wizard", "f")
        wizz.privileges.add("wizard")
        rat.insert(Item("thing2"), wizz)
        self.assertEqual(2, rat.inventory_size)
        stuff = [Item("thing")]
        with self.assertRaises(AssertionError):
            rat.init_inventory(stuff)
        rat = Living("rat", "n", race="rodent")
        rat.init_inventory(stuff)
        self.assertEqual(1, rat.inventory_size)

    def test_move_notify(self):
        class LocationNotify(Location):
            def notify_npc_left(self, npc: Living, target_location: Location) -> None:
                self.npc_left = npc
                self.npc_left_target = target_location

            def notify_npc_arrived(self, npc: Living, previous_location: Location) -> None:
                self.npc_arrived = npc
                self.npc_arrived_from = previous_location

            def notify_player_left(self, player: Player, target_location: Location) -> None:
                self.player_left = player
                self.player_left_target = target_location

            def notify_player_arrived(self, player: Player, previous_location: Location) -> None:
                self.player_arrived = player
                self.player_arrived_from = previous_location

        npc = Living("rat", "m", race="rodent")
        room1 = LocationNotify("room1")
        room2 = LocationNotify("room2")
        room1.insert(npc, None)
        npc.move(room2)
        pubsub.sync()
        self.assertEqual(room2, npc.location)
        self.assertEqual(npc, room1.npc_left)
        self.assertEqual(room2, room1.npc_left_target)
        self.assertEqual(npc, room2.npc_arrived)
        self.assertEqual(room1, room2.npc_arrived_from)


class TestAggressiveNpc(unittest.TestCase):
    def test_init_inventory(self):
        rat = Living("rat", "n", race="rodent")
        rat.aggressive = True
        with self.assertRaises(ActionRefused):
            rat.insert(Item("thing"), None)
        rat.insert(Item("thing"), rat)
        wizz = Player("wizard", "f")
        wizz.privileges.add("wizard")
        rat.insert(Item("thing2"), wizz)
        self.assertEqual(2, rat.inventory_size)
        stuff = [Item("thing")]
        with self.assertRaises(AssertionError):
            rat.init_inventory(stuff)
        rat = Living("rat", "n", race="rodent")
        rat.aggressive = True
        rat.init_inventory(stuff)
        self.assertEqual(1, rat.inventory_size)


class TestDescriptions(unittest.TestCase):
    def test_name(self):
        item = Item("key")
        self.assertEqual("key", item.name)
        self.assertEqual("key", item.title)
        self.assertEqual("", item.description)
        item = Item("KEY")
        self.assertEqual("key", item.name)
        self.assertEqual("KEY", item.title)
        self.assertEqual("", item.description)

    def test_title(self):
        item = Item("key", "rusty old key")
        self.assertEqual("key", item.name)
        self.assertEqual("rusty old key", item.title)
        self.assertEqual("", item.description)

    def test_description(self):
        item = Item("key", "rusty old key", "a small old key that's rusted")
        self.assertEqual("key", item.name)
        self.assertEqual("rusty old key", item.title)
        self.assertEqual("a small old key that's rusted", item.description)
        item = Item("key", "rusty old key",
                    """
                    a very small, old key that's rusted
                    """)
        self.assertEqual("key", item.name)
        self.assertEqual("rusty old key", item.title)
        self.assertEqual("a very small, old key that's rusted", item.description)

    def test_extradesc(self):
        item = Item("key", "some key")
        item.extra_desc = {"alias1": "first alias desc", "foo": "bar"}
        item.add_extradesc({"alias2", "alias3"}, "more description text")
        self.assertEqual("first alias desc", item.extra_desc["alias1"])
        self.assertEqual("more description text", item.extra_desc["alias3"])

    def test_dynamic_description_by_using_property(self):
        import time

        class DynamicThing(Item):
            @property
            def description(self):
                return "The watch shows %f" % time.time()

            @property
            def title(self):
                return "a watch showing %f" % time.time()

        watch = DynamicThing("watch")
        title1 = watch.title
        descr1 = watch.description
        self.assertTrue(descr1.startswith("The watch shows "))
        self.assertTrue(title1.startswith("a watch showing "))
        time.sleep(0.02)
        self.assertNotEqual(title1, watch.title)
        self.assertNotEqual(descr1, watch.description)


class TestDestroy(unittest.TestCase):
    def setUp(self):
        mud_context.driver = TestDriver()

    def test_destroy_base(self):
        ctx = Context(None, None, None, None)
        o = Item("x")
        o.destroy(ctx)

    def test_destroy_loc(self):
        ctx = Context(None, None, None, None)
        loc = Location("loc")
        i = Item("item")
        liv = Living("rat", "n", race="rodent")
        loc.add_exits([Exit("north", "somewhere", "exit to somewhere")])
        player = Player("julie", "f")
        player.privileges = {"wizard"}
        player.create_wiretap(loc)
        loc.init_inventory([i, liv, player])
        self.assertTrue(len(loc.exits) > 0)
        self.assertTrue(len(loc.items) > 0)
        self.assertTrue(len(loc.livings) > 0)
        self.assertEqual(loc, player.location)
        self.assertEqual(loc, liv.location)
        loc.destroy(ctx)
        self.assertTrue(len(loc.exits) == 0)
        self.assertTrue(len(loc.items) == 0)
        self.assertTrue(len(loc.livings) == 0)
        self.assertEqual(_limbo, player.location)
        self.assertEqual(_limbo, liv.location)

    def test_destroy_player(self):
        ctx = Context(None, None, None, None)
        loc = Location("loc")
        player = Player("julie", "f")
        player.privileges = {"wizard"}
        player.create_wiretap(loc)
        player.insert(Item("key"), player)
        loc.init_inventory([player])
        self.assertEqual(loc, player.location)
        self.assertTrue(len(player.inventory) > 0)
        self.assertTrue(player in loc.livings)
        player.destroy(ctx)
        import gc
        gc.collect()
        self.assertTrue(len(player.inventory) == 0)
        self.assertFalse(player in loc.livings)
        self.assertIsNone(player.location, "destroyed player should end up nowhere (None)")

    def test_destroy_item(self):
        thing = Item("thing")
        ctx = Context(driver=mud_context.driver, clock=None, config=None, player_connection=None)
        thing.destroy(ctx)

    def test_destroy_deferreds(self):
        ctx = Context(driver=mud_context.driver, clock=None, config=None, player_connection=None)
        thing = Item("thing")
        player = Player("julie", "f")
        wolf = Living("wolf", "m")
        loc = Location("loc")
        mud_context.driver.defer(datetime.datetime.now(), thing.move)
        mud_context.driver.defer(datetime.datetime.now(), player.move)
        mud_context.driver.defer(datetime.datetime.now(), wolf.move)
        mud_context.driver.defer(datetime.datetime.now(), loc.move)
        self.assertEqual(4, len(mud_context.driver.deferreds))
        thing.destroy(ctx)
        player.destroy(ctx)
        wolf.destroy(ctx)
        loc.destroy(ctx)
        self.assertEqual(0, len(mud_context.driver.deferreds), "all deferreds must be removed")


class TestContainer(unittest.TestCase):
    def test_container_contains(self):
        bag = Container("bag")
        key = Item("key")
        self.assertEqual(0, len(bag.inventory))
        self.assertEqual(0, bag.inventory_size)
        npc = Living("julie", "f")
        bag.insert(key, npc)
        self.assertTrue(key in bag)
        self.assertEqual(1, bag.inventory_size)
        bag.remove(key, npc)
        self.assertEqual(0, bag.inventory_size)
        self.assertFalse(key in bag)
        with self.assertRaises(ActionRefused):
            bag.remove("not an item", npc)
        separate_item = Item("key2")
        with self.assertRaises(KeyError):
            bag.remove(separate_item, npc)

    def test_allowance(self):
        bag = Container("bag")
        key = Item("key")
        player = Player("julie", "f")
        with self.assertRaises(AssertionError):
            bag.insert(None, player)
        bag.insert(key, player)
        with self.assertRaises(AssertionError):
            bag.remove(None, player)
        bag.remove(key, player)
        bag.allow_item_move(player)
        with self.assertRaises(ActionRefused):
            key.insert(bag, player)
        with self.assertRaises(ActionRefused):
            key.remove(bag, player)
        self.assertFalse(key in bag)
        with self.assertRaises(ActionRefused):
            bag in key

    def test_inventory(self):
        bag = Container("bag")
        key = Item("key")
        thing = Item("gizmo")
        player = Player("julie", "f")
        with self.assertRaises(ActionRefused):
            thing in key  # can't check for containment in an Item
        self.assertFalse(thing in bag)
        with self.assertRaises(ActionRefused):
            key.insert(thing, player)  # can't add stuf to an Item
        bag.insert(thing, player)
        self.assertTrue(thing in bag)
        self.assertTrue(isinstance(bag.inventory, (set, frozenset)))
        self.assertEqual(1, bag.inventory_size)
        with self.assertRaises(AttributeError):
            bag.inventory_size = 5
        with self.assertRaises(AttributeError):
            bag.inventory = None
        with self.assertRaises(AttributeError):
            bag.inventory.add(5)

    def test_title(self):
        bag = Container("bag", "leather bag", "a small leather bag")
        stone = Item("stone")
        player = Player("julie", "f")
        self.assertEqual("bag", bag.name)
        self.assertEqual("leather bag", bag.title)
        self.assertEqual("a small leather bag", bag.description)
        bag.move(player, player)
        self.assertEqual("bag", bag.name)
        self.assertEqual("leather bag", strip_text_styles(bag.title))
        self.assertEqual("a small leather bag", strip_text_styles(bag.description))
        stone.move(bag, player)
        self.assertEqual("bag", bag.name)
        self.assertEqual("leather bag", strip_text_styles(bag.title))
        self.assertEqual("a small leather bag", strip_text_styles(bag.description))


class TestItem(unittest.TestCase):
    def test_insertremove(self):
        key = Item("key")
        thing = Item("gizmo")
        player = Player("julie", "f")
        with self.assertRaises(ActionRefused):
            key.remove(None, player)
        with self.assertRaises(ActionRefused):
            key.remove(thing, player)
        with self.assertRaises(ActionRefused):
            key.insert(None, player)
        with self.assertRaises(ActionRefused):
            key.insert(thing, player)
        key.allow_item_move(player)
        with self.assertRaises(ActionRefused):
            key.inventory
        with self.assertRaises(ActionRefused):
            key.inventory_size

    def test_move(self):
        hall = Location("hall")
        person = Living("person", "m", race="human")
        monster = Living("dragon", "f", race="dragon")
        monster.aggressive = True
        key = Item("key")
        stone = Item("stone")
        hall.init_inventory([person, key])
        stone.move(hall, person)
        wiretap = Wiretap(hall)
        self.assertTrue(person in hall)
        self.assertTrue(key in hall)
        key.contained_in = person   # hack to force move to actually check the source container
        with self.assertRaises(KeyError):
            key.move(person, person)
        key.contained_in = hall   # put it back as it was
        key.move(person, person)
        self.assertFalse(key in hall)
        self.assertTrue(key in person)
        self.assertEqual([], wiretap.msgs, "item.move() should be silent")
        with self.assertRaises(ActionRefused) as x:
            key.move(monster, person)  # aggressive monster should fail
        self.assertTrue("not a good idea" in str(x.exception))
        monster.aggressive = False
        with self.assertRaises(ActionRefused) as x:
            key.move(monster, person)   # non-aggressive should fail but differently
        self.assertTrue("doesn't want" in str(x.exception))
        stone.move(monster, monster)
        self.assertTrue(stone in monster)

    def test_lang(self):
        thing = Item("thing")
        self.assertEqual("it", thing.objective)
        self.assertEqual("its", thing.possessive)
        self.assertEqual("it", thing.subjective)
        self.assertEqual("n", thing.gender)

    def test_location(self):
        thingy = Item("thing")
        with self.assertRaises(TypeError):
            thingy.location = "foobar"
        hall = Location("hall")
        thingy.location = hall
        self.assertEqual(hall, thingy.contained_in)
        self.assertEqual(hall, thingy.location)
        person = Living("person", "m", race="human")
        key = Item("key")
        backpack = Container("backpack")
        person.insert(backpack, person)
        self.assertIsNone(key.contained_in)
        self.assertIsNone(key.location)
        self.assertTrue(backpack in person)
        self.assertEqual(person, backpack.contained_in)
        self.assertEqual(_limbo, backpack.location)
        hall.init_inventory([person, key])
        self.assertEqual(hall, key.contained_in)
        self.assertEqual(hall, key.location)
        self.assertEqual(hall, backpack.location)
        key.move(backpack, person)
        self.assertEqual(backpack, key.contained_in)
        self.assertEqual(hall, key.location)


class TestMudObject(unittest.TestCase):
    def test_basics(self):
        try:
            x = Item("name", "the title", "description")
            self.fail("assertion error expected")
        except AssertionError:
            pass
        x = Item("name", "title", "description")
        x.init()
        x.heartbeat(None)
        with self.assertRaises(ActionRefused):
            x.activate(None)
        with self.assertRaises(ActionRefused):
            x.deactivate(None)
        with self.assertRaises(ActionRefused):
            x.manipulate("frobnitz", None)
        with self.assertRaises(ActionRefused):
            x.read(None)
        x.destroy(Context(None, None, None, None))

    def test_nocreate(self):
        with self.assertRaises(TypeError):
            MudObject("name")


class TestFunctions(unittest.TestCase):
    def test_clone(self):
        item = Item("thing", "description")
        item.aliases = ["a1", "a2"]
        item2 = clone(item)
        self.assertNotEqual(item, item2)
        item2.aliases.append("a3")
        self.assertNotEqual(item.aliases, item2.aliases)
        player = Player("julie", "f")
        with self.assertRaises(TypeError):
            clone(player)   # can only clone Items
        class ItemWithStuff(Item):
            @property
            def inventory(self):
                return ["stuff"]
            @property
            def inventory_size(self):
                return len(self.inventory)
        item2=ItemWithStuff("weird")
        with self.assertRaises(ValueError):
            clone(item2)   # can't clone something with stuff in it


if __name__ == '__main__':
    unittest.main()
