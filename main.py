"""Flask application to display live memory information from
   PLA onto a map"""
import json
import struct

import requests
from flask import Flask, render_template, request
import nxreader
from pa8 import Pa8
from xoroshiro import XOROSHIRO

from pyfladesk import init_gui

from pla_live_map_lib import calc_from_seed, generate_from_seed, find_slots, \
    slot_to_pokemon, next_filtered, generate_passive_search_paths

with open("./static/resources/text_natures.txt",
          encoding="utf-8") as text_natures:
    NATURES = text_natures.read().split("\n")
with open("./static/resources/text_species.txt",
          encoding="utf-8") as text_species:
    SPECIES = text_species.read().split("\n")
PLAYER_LOCATION_PTR = "[[[[[[main+42B3558]+88]+90]+1F0]+18]+80]+90"
SPAWNER_PTR = "[[main+4268ee0]+330]"
PARTY_PTR = "[[[main+4269000]+d0]+58]"
WILD_PTR = "[[[[main+4268f00]+b0]+e0]+d0]"
OUTBREAK_PTR = "[[[[main+427C470]+2B0]+58]+18]"
CUSTOM_MARKERS = {
    "obsidianfieldlands": {
        "camp": {
            "coords": [
                365.36,
                52,
                136.1
            ],
            "faIcon": "campground",
        }
    },
    "crimsonmirelands": {
        "camp": {
            "coords": [
                242.45,
                55.64,
                435.84
            ],
            "faIcon": "campground",
        }
    },
    "cobaltcoastlands": {
        "camp": {
            "coords": [
                71.06,
                45.16,
                625.38
            ],
            "faIcon": "campground",
        }
    },
    "coronethighlands": {
        "camp": {
            "coords": [
                892.75,
                36.45,
                922.92
            ],
            "faIcon": "campground",
        }
    },
    "alabastericelands": {
        "camp": {
            "coords": [
                533.77,
                31.13,
                912.42
            ],
            "faIcon": "campground",
        }
    }
}

with open("config.json", "r", encoding="utf-8") as config:
    IP_ADDRESS = json.load(config)["IP"]

app = Flask(__name__)
reader = nxreader.NXReader(IP_ADDRESS)


@app.route("/")
def root():
    """Display index.html at the root of the application"""
    return render_template('index.html')


@app.route("/map/<name>")
def load_map(name):
    """Read markers and generate map based on location"""
    url = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main" \
          "/Resources/" \
          f"pla_spawners/jsons/{name}.json"
    markers = json.loads(requests.get(url).text)
    with open(f"./static/resources/{name}.json", encoding="utf-8") as slot_file:
        slots = json.load(slot_file)

    return render_template('map.html',
                           markers=markers.values(),
                           map_name=name,
                           custom_markers=json.dumps(CUSTOM_MARKERS[name]),
                           slots=slots)


def find_slot_range(time, weather, species, sp_slots):
    """Find slot range of a species for a spawner"""
    values = find_slots(time, weather, sp_slots)
    pokemon = list(values.keys())
    slot_values = list(values.values())
    if not species in pokemon:
        return 0, 0, 0
    start = sum(slot_values[:pokemon.index(species)])
    end = start + values[species]
    return start, end, sum(slot_values)


def generate_mass_outbreak(main_rng, rolls, spawns, poke_filter):
    """Generate the current set of a mass outbreak and return a string representing it along with
       a bool to show if a pokemon passing poke_filter is present"""
    # pylint: disable=too-many-locals
    # this many locals is appropriate to display all the information about
    # the mass outbreak that a user might want
    display = ""
    filtered_present = False
    for init_spawn in range(1, 5):
        generator_seed = main_rng.next()
        main_rng.next()  # spawner 1's seed, unused
        fixed_rng = XOROSHIRO(generator_seed)
        slot = (fixed_rng.next() / (2 ** 64) * 101)
        alpha = slot >= 100
        fixed_seed = fixed_rng.next()
        encryption_constant,pid,ivs,ability,gender,nature,shiny = \
            generate_from_seed(fixed_seed,rolls,3 if alpha else 0)
        display += f"<b>Init Spawn {init_spawn}</b> <b>Shiny: " \
                   f"<font color=\"{'green' if shiny else 'red'}\">{shiny}</font></b><br>" \
                   f"<b>Alpha: <font color=\"{'green' if alpha else 'red'}\">" \
                   f"{alpha}</font></b><br>" \
                   f"EC: {encryption_constant:08X} PID: {pid:08X}<br>" \
                   f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>" \
                   f"{'/'.join(str(iv) for iv in ivs)}<br>"
        filtered = ((poke_filter['shinyFilterCheck'] and not shiny)
                    or poke_filter[
                        'outbreakAlphaFilter'] and not 100 <= slot < 101)
        filtered_present |= not filtered
    group_seed = main_rng.next()
    main_rng.reseed(group_seed)
    respawn_rng = XOROSHIRO(group_seed)
    for respawn in range(1, spawns - 3):
        generator_seed = respawn_rng.next()
        respawn_rng.next()  # spawner 1's seed, unused
        respawn_rng.reseed(respawn_rng.next())
        fixed_rng = XOROSHIRO(generator_seed)
        slot = (fixed_rng.next() / (2 ** 64) * 101)
        alpha = slot >= 100
        fixed_seed = fixed_rng.next()
        encryption_constant,pid,ivs,ability,gender,nature,shiny = \
            generate_from_seed(fixed_seed,rolls,3 if alpha else 0)
        display += f"<b>Respawn {respawn}</b> Shiny: " \
                   f"<b><font color=\"{'green' if shiny else 'red'}\">{shiny}</font></b><br>" \
                   f"<b>Alpha: <font color=\"{'green' if alpha else 'red'}\">" \
                   f"{alpha}</font></b><br>" \
                   f"EC: {encryption_constant:08X} PID: {pid:08X}<br>" \
                   f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>" \
                   f"{'/'.join(str(iv) for iv in ivs)}<br>"
        filtered = ((poke_filter['shinyFilterCheck'] and not shiny)
                    or poke_filter[
                        'outbreakAlphaFilter'] and not 100 <= slot < 101)
        filtered_present |= not filtered
    return display, filtered_present


def next_filtered_mass_outbreak(main_rng, rolls, spawns, poke_filter):
    """Find the next pokemon of a mass outbreak that passes poke_filter
       and return a string representing it"""
    filtered_present = False
    advance = 0
    while not filtered_present:
        advance += 1
        display, filtered_present = generate_mass_outbreak(main_rng, rolls,
                                                           spawns, poke_filter)
    return f"<b>Advance: {advance}</b><br>{display}"


def generate_mass_outbreak_aggressive_path(group_seed, rolls, steps,
                                           poke_filter, uniques, storage):
    """Generate all the pokemon of an outbreak based on a provided aggressive path"""
    # pylint: disable=too-many-locals, too-many-arguments
    # the generation is unique to each path, no use in splitting this function
    main_rng = XOROSHIRO(group_seed)
    for init_spawn in range(1, 5):
        generator_seed = main_rng.next()
        main_rng.next()  # spawner 1's seed, unused
        fixed_rng = XOROSHIRO(generator_seed)
        slot = (fixed_rng.next() / (2 ** 64) * 101)
        alpha = slot >= 100
        fixed_seed = fixed_rng.next()
        encryption_constant, pid, ivs, ability, gender, nature, shiny = \
            generate_from_seed(fixed_seed, rolls, 3 if alpha else 0)
        filtered = ((poke_filter['shinyFilterCheck'] and not shiny)
                    or poke_filter['outbreakAlphaFilter'] and not alpha)
        if not filtered and not fixed_seed in uniques:
            uniques.add(fixed_seed)
            storage.append(
                f"<b>Init Spawn {init_spawn} Shiny: "
                f"<font color=\"{'green' if shiny else 'red'}\">{shiny}</font></b><br>"
                f"<b>Alpha: <font color=\"{'green' if alpha else 'red'}\">"
                f"{alpha}</font></b><br>"
                f"EC: {encryption_constant:08X} PID: {pid:08X}<br>"
                f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>"
                f"{'/'.join(str(iv) for iv in ivs)}")
    group_seed = main_rng.next()
    respawn_rng = XOROSHIRO(group_seed)
    for step_i, step in enumerate(steps):
        for pokemon in range(1, step + 1):
            generator_seed = respawn_rng.next()
            respawn_rng.next()  # spawner 1's seed, unused
            fixed_rng = XOROSHIRO(generator_seed)
            slot = (fixed_rng.next() / (2 ** 64) * 101)
            alpha = slot >= 100
            fixed_seed = fixed_rng.next()
            encryption_constant,pid,ivs,ability,gender,nature,shiny = \
                generate_from_seed(fixed_seed,rolls,3 if alpha else 0)
            filtered = ((poke_filter['shinyFilterCheck'] and not shiny)
                      or poke_filter['outbreakAlphaFilter'] and not alpha)
            if not filtered and not fixed_seed in uniques:
                uniques.add(fixed_seed)
                storage.append(
                    f"<b>Path: {'|'.join(str(s) for s in steps[:step_i] + [pokemon])} "
                    f"Spawns: {sum(steps[:step_i]) + pokemon + 4} Shiny: "
                    f"<font color=\"{'green' if shiny else 'red'}\">{shiny}</font></b><br>"
                    f"<b>Alpha: <font color=\"{'green' if alpha else 'red'}\">"
                    f"{alpha}</font></b><br>"
                    f"EC: {encryption_constant:08X} PID: {pid:08X}<br>"
                    f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>"
                    f"{'/'.join(str(iv) for iv in ivs)}"
                )
        respawn_rng = XOROSHIRO(respawn_rng.next())


def get_final(spawns):
    """Get the final path that will be generated to know when to stop
    aggressive recursion """
    spawns -= 4
    path = [4] * (spawns // 4)
    if spawns % 4 != 0:
        path.append(spawns % 4)
    return path

def aggressive_outbreak_pathfind(group_seed,
                                 rolls,
                                 spawns,
                                 poke_filter,
                                 step=0,
                                 steps=None,
                                 uniques=None,
                                 storage=None):
    """Recursively pathfind to possible shinies for the current outbreak via
    multi battles """
    # pylint: disable=too-many-arguments
    # can this algo be improved?
    if steps is None or uniques is None or storage is None:
        steps = []
        uniques = set()
        storage = []
    _steps = steps.copy()
    if step != 0:
        _steps.append(step)
    if sum(_steps) + step < spawns - 4:
        for _step in range(1, min(5, (spawns - 4) - sum(_steps))):
            if aggressive_outbreak_pathfind(group_seed,
                                            rolls,
                                            spawns,
                                            poke_filter,
                                            _step,
                                            _steps,
                                            uniques,
                                            storage) is not None:
                return storage
    else:
        _steps.append(spawns - sum(_steps) - 4)
        generate_mass_outbreak_aggressive_path(group_seed, rolls, _steps,
                                               poke_filter, uniques, storage)
        if _steps == get_final(spawns):
            return storage
    return None


def next_filtered_aggressive_outbreak_pathfind(group_seed, rolls, spawns,
                                               poke_filter):
    """Check the next outbreak advances until an aggressive path to a pokemon that
       passes poke_filter exists"""
    main_rng = XOROSHIRO(group_seed)
    result = []
    advance = -1
    while len(result) == 0:
        if advance != -1:
            for _ in range(4 * 2):
                main_rng.next()
            group_seed = main_rng.next()
            main_rng.reseed(group_seed)
        advance += 1
        result = aggressive_outbreak_pathfind(group_seed, rolls, spawns,
                                              poke_filter)
    info = '<br>'.join(result)
    return f"<b>Advance: {advance}</b><br>{info}"


@app.route('/read-battle', methods=['GET'])
def read_battle():
    """Read all battle pokemon and return the information as an html
    formatted string """
    display = ""
    party_count = reader.read_pointer_int(f"{PARTY_PTR}+88", 1)
    wild_count = reader.read_pointer_int(f"{WILD_PTR}+1a0", 1) \
                 - party_count
    if wild_count > 30:
        wild_count = 0
    for i in range(wild_count):
        pkm = Pa8(
            reader.read_pointer(f"{WILD_PTR}+{0xb0 + 8 * (i + party_count):X}"
                                "]+70]+60]+98]+10]", Pa8.STOREDSIZE))
        pokemon_name = f"{SPECIES[pkm.species]}" \
                       f"{('-' + str(pkm.form_index)) if pkm.form_index > 0 else ''} " \
                       f"{'' if pkm.shiny_type == 0 else '⋆' if pkm.shiny_type == 1 else '◇'}"
        pokemon_info = f"EC: {pkm.encryption_constant:08X}<br>" \
                       f"PID: {pkm.pid:08X}<br>" \
                       f"Nature: {NATURES[pkm.nature]}<br>" \
                       f"Ability: {pkm.ability_string}<br>" \
                       f"IVs: {'/'.join(str(iv) for iv in pkm.ivs)}"
        if pkm.is_valid:
            display += f"<button type=\"button\" class=\"collapsible\" " \
                       f"data-for=\"battle{i}\" onclick=collapsibleOnClick()>{i + 1} " \
                       f"{pokemon_name}</button>" \
                       f"<div class=\"info\" id=\"battle{i}\">{pokemon_info}</div><br>"
    return display


@app.route('/read-mass-outbreak', methods=['POST'])
def read_mass_outbreak():
    """Read current mass outbreak information and predict next pokemon that
    passes filter """
    url = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main" \
          "/Resources/" \
          f"pla_spawners/jsons/{request.json['name']}.json"
    minimum = int(list(json.loads(requests.get(url).text).keys())[-1]) - 15
    group_id = minimum + 30
    group_seed = 0
    while group_seed == 0 and group_id != minimum:
        group_id -= 1
        print(f"Finding group_id {minimum - group_id + 30}/30")
        group_seed = reader.read_pointer_int(
            f"{SPAWNER_PTR}+{0x70 + group_id * 0x440 + 0x408:X}", 8)
    if group_id == minimum:
        print("No mass outbreak found")
        return json.dumps(["No mass outbreak found", "No mass outbreak found"])
    print(f"Found group_id {group_id}")
    generator_seed = reader.read_pointer_int(
        f"{SPAWNER_PTR}+{0x70 + group_id * 0x440 + 0x20:X}", 8)
    group_seed = (generator_seed - 0x82A2B175229D6A5B) & 0xFFFFFFFFFFFFFFFF
    if request.json['spawns'] == -1:
        for i in range(4):
            spawns = reader.read_pointer_int(
                f"{OUTBREAK_PTR}+{0x60 + i * 0x50:X}", 1)
            if 10 <= spawns <= 15:
                request.json['spawns'] = spawns
                break
        print(f"Spawns: {request.json['spawns']}")
    if request.json['aggressivePath']:
        # should display multiple aggressive paths like whats done with passive
        display = ["",
                   f"Group Seed: {group_seed:X}<br>"
                   + next_filtered_aggressive_outbreak_pathfind(group_seed,
                                                                request.json[
                                                                    'rolls'],
                                                                request.json[
                                                                    'spawns'],
                                                                request.json[
                                                                    'filter'])]
    elif request.json['passivePath']:
        info, paths_list = generate_passive_search_paths(group_seed,
                              request.json['rolls'],
                              request.json['spawns'],
                              request.json['passiveMoveLimit'],
                              request.json['filter']['shinyFilterCheck'],
                              request.json['filter']['outbreakAlphaFilter'],
                              not request.json['passiveFindFirst'])
        display = ["",f"Group Seed: {group_seed:X}<br>"]
        if len(info) == 0:
            display[1] += "<b>No paths found</b>"
        for seed, info in info.items():
            paths = paths_list[seed]
            display[1] += "<b>Paths:<br>"
            for effective_path in paths:
                display[1] += \
                    f"{'|'.join(str(effective_step) for effective_step in effective_path)}<br>"
            display[1] += f"</b>{info}<br>"
    else:
        main_rng = XOROSHIRO(group_seed)
        display = [f"Group Seed: {group_seed:X}<br>"
                   + generate_mass_outbreak(main_rng,
                                            request.json['rolls'],
                                            request.json['spawns'],
                                            request.json['filter'])[0],
                   next_filtered_mass_outbreak(main_rng,
                                               request.json['rolls'],
                                               request.json['spawns'],
                                               request.json['filter'])]
    return json.dumps(display)


@app.route('/check-possible', methods=['POST'])
def check_possible():
    """Check spawners that can spawn a given species"""
    print(request.json)
    url = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main" \
          "/Resources/" \
          f"pla_spawners/jsons/{request.json['name']}.json"
    markers = json.loads(requests.get(url).text)
    possible = {}
    for group_id, marker in markers.items():
        with open(f"./static/resources/{request.json['name']}.json",
                  encoding="utf-8") as slot_file:
            sp_slots = \
                json.load(slot_file)[marker['name']]
        minimum, maximum, total \
            = find_slot_range(request.json["filter"]["timeSelect"],
                              request.json["filter"]["weatherSelect"],
                              request.json["filter"]["speciesSelect"],
                              sp_slots)
        if total:
            possible[group_id] = (maximum - minimum) / total * 100
    return json.dumps(possible)


@app.route('/read-seed', methods=['POST'])
def read_seed():
    """Read current information and next advance that passes filter for a
    spawner """
    # pylint: disable=too-many-locals
    group_id = request.json['groupID']
    thresh = request.json['thresh']
    url = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main" \
          "/Resources/" \
          f"pla_spawners/jsons/{request.json['map']}.json"
    with open(f"./static/resources/{request.json['map']}.json",
              encoding="utf-8") as slot_file:
        sp_slots = \
            json.load(slot_file)[
                json.loads(requests.get(url).text)[str(group_id)]['name']]

    generator_seed = reader.read_pointer_int(f"{SPAWNER_PTR}"
                                             f"+{0x70 + group_id * 0x440 + 0x20:X}",
                                             8)
    group_seed = (generator_seed - 0x82A2B175229D6A5B) & 0xFFFFFFFFFFFFFFFF
    encryption_constant, pid, ivs, ability, gender, nature, shiny, slot \
        = calc_from_seed(group_seed, request.json['initSpawn'],
                         request.json['filter']['slotTotal'],
                         request.json['rolls'], request.json['ivs'])

    species = slot_to_pokemon(find_slots(request.json["filter"]["timeSelect"],
                                         request.json["filter"][
                                             "weatherSelect"],
                                         sp_slots), slot)

    display = f"Generator Seed: {generator_seed:X}<br>" \
              f"Species: {species}<br>" \
              f"Shiny: <font color=\"{'green' if shiny else 'red'}\"><b>{shiny}</b></font><br>" \
              f"EC: {encryption_constant:X} PID: {pid:X}<br>" \
              f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>" \
              f"{'/'.join(str(iv) for iv in ivs)}<br>"
    if request.json['filter']['filterSpeciesCheck']:
        request.json['filter']['minSlotFilter'], \
        request.json['filter']['maxSlotFilter'], \
        request.json['filter']['slotTotal'] \
            = find_slot_range(request.json["filter"]["timeSelect"],
                              request.json["filter"]["weatherSelect"],
                              request.json["filter"]["speciesSelect"],
                              sp_slots)
        request.json['filter']['slotFilterCheck'] = True

    adv, slot, encryption_constant, pid, ivs, ability, gender, nature, shiny \
        = next_filtered(group_seed,
                        request.json['rolls'],
                        request.json['ivs'],
                        request.json['initSpawn'],
                        50000,
                        request.json['filter']["slotTotal"],
                        request.json['filter']["shinyFilterCheck"],
                        request.json['filter']["slotFilterCheck"],
                        request.json['filter']["minSlotFilter"],
                        request.json['filter']["maxSlotFilter"],
                        request.json['filter']["outbreakAlphaFilter"])

    if adv == -1:
        return "Impossible slot filters for this spawner"
    if adv == -2:
        return "No results before limit (50000)"
    if adv <= thresh:
        display += f"Next Filtered: <font color=\"green\"><b>{adv}</b></font" \
                   f"><br> "
    else:
        display += f"Next Filtered: {adv} <br>"

    species = slot_to_pokemon(find_slots(request.json["filter"]["timeSelect"],
                                         request.json["filter"][
                                             "weatherSelect"],
                                         sp_slots), slot)
    display += f"Species: {species}<br>" \
               f"Shiny: <font color=\"{'green' if shiny else 'red'}\"><b>{shiny}</b></font><br>" \
               f"EC: {encryption_constant:X} PID: {pid:X}<br>" \
               f"Nature: {NATURES[nature]} Ability: {ability} Gender: {gender}<br>" \
               f"{'/'.join(str(iv) for iv in ivs)}<br>"
    return display


@app.route('/teleport', methods=['POST'])
def teleport():
    """Teleport the player to provided coordinates"""
    coordinates = request.json['coords']
    print(f"Teleporting to {coordinates}")
    position_bytes = struct.pack('fff', *coordinates)
    reader.write_pointer(PLAYER_LOCATION_PTR,
                         f"{int.from_bytes(position_bytes, 'big'):024X}")
    return ""


@app.route('/read-coords', methods=['GET'])
def read_coords():
    """Read the players current position"""
    pos = struct.unpack('fff', reader.read_pointer(PLAYER_LOCATION_PTR, 12))
    coords = {
        "x": pos[0],
        "y": pos[1],
        "z": pos[2]
    }
    return json.dumps(coords)


@app.route('/update-positions', methods=['GET'])
def update_positions():
    """Scan all active spawns"""
    spawns = {}
    size = reader.read_pointer_int(f"{SPAWNER_PTR}+18", 4)
    size = int(size // 0x40 - 1)
    print(f"Checking up to index {size}")
    for index in range(0, size):
        if index % int(size // 100) == 0:
            print(f"{index / size * 100}% done scanning")
        position_bytes = reader.read_pointer(
            f"{SPAWNER_PTR}+{0x70 + index * 0x40:X}", 12)
        seed = reader.read_pointer_int(f"{SPAWNER_PTR}+{0x90 + index * 0x40:X}",
                                       12)
        pos = struct.unpack('fff', position_bytes)
        if not (seed == 0 or pos[0] < 1 or pos[1] < 1 or pos[2] < 1):
            print(
                f"Active: spawner_id {index} {pos[0]},{pos[1]},{pos[2]} {seed:X}")
            spawns[str(index)] = {"x": pos[0],
                                  "y": pos[1],
                                  "z": pos[2],
                                  "seed": seed}
    return json.dumps(spawns)


@app.route('/check-near', methods=['POST'])
def check_near():
    """Check all spawners' nearest advance that passes filters to update
    icons """
    # pylint: disable=too-many-locals store these locals before the loop to
    # avoid accessing dictionary items repeatedly
    thresh = request.json['thresh']
    name = request.json['name']
    url = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main" \
          "/Resources/" \
          f"pla_spawners/jsons/{name}.json"
    markers = json.loads(requests.get(url).text)
    maximum = list(markers.keys())[-1]
    near = []
    poke_filter = request.json['filter']
    time = request.json["filter"]["timeSelect"]
    weather = request.json["filter"]["weatherSelect"]
    species = request.json["filter"]["speciesSelect"]
    with open(f"./static/resources/{name}.json", encoding="utf-8") as slot_file:
        slots = json.load(slot_file)
    for group_id, marker in markers.items():
        if poke_filter['filterSpeciesCheck']:
            sp_slots = slots[markers[str(group_id)]['name']]
            poke_filter['minSlotFilter'], \
            poke_filter['maxSlotFilter'], \
            poke_filter['slotTotal'] \
                = find_slot_range(time,
                                  weather,
                                  species,
                                  sp_slots)
            poke_filter['slotFilterCheck'] = True
        print(f"Checking group_id {group_id}/{maximum}")
        generator_seed = reader.read_pointer_int(f"{SPAWNER_PTR}"
                                                 f"+{0x70 + int(group_id) * 0x440 + 0x20:X}",
                                                 8)
        group_seed = (generator_seed - 0x82A2B175229D6A5B) & 0xFFFFFFFFFFFFFFFF
        adv, _, _, _, _, _, _, _, _ = \
            next_filtered(group_seed,
                          request.json['rolls'],
                          marker['ivs'],
                          request.json['initSpawn'],
                          50000,
                          request.json['filter']["slotTotal"],
                          request.json['filter']["shinyFilterCheck"],
                          request.json['filter']["slotFilterCheck"],
                          request.json['filter']["minSlotFilter"],
                          request.json['filter']["maxSlotFilter"],
                          request.json['filter']["outbreakAlphaFilter"])
        if 0 <= adv <= thresh:
            near.append(group_id)
    return json.dumps(near)


if __name__ == '__main__':
    init_gui(app, port=8080, window_title="PLA Live Map")
