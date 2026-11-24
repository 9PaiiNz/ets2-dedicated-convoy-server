#!/usr/bin/python3

import os
import re
import subprocess
import sys
import logging
import os.path
from typing import Any, TypeVar, Union, overload


def print_debug_env():
    logging.debug("--------- CONFIG ---------")
    logging.debug(f"Version: {get_version()}")
    logging.debug(f"App ID: {getenv('APP_ID')}")
    logging.debug(f"Custom Branch: {getenv('ETS_SERVER_BRANCH')}")
    logging.debug(f"Update: {is_truthy(getenv('ETS_SERVER_UPDATE_ON_START'))}")
    logging.debug(f"Players: {getenv('ETS_SERVER_MAX_PLAYERS')}")
    logging.debug(f"Config Path: {getenv('ETS_SERVER_CONFIG_FILE_PATH')}")


T = TypeVar("T")

@overload
def getenv(key: str) -> str | None: ...


@overload
def getenv(key: str, default: T) -> str | T: ...


def getenv(key: str, default: T | None = None) -> T:
    """
    ENV helper to support variables with ATS_ and ETS_ prefixes.
    """
    if key.startswith("ETS_"):
        key_ats = "ATS_" + key[4:]
        return os.getenv(key, os.getenv(key_ats, default))

    return os.getenv(key, default)


def server_files_exist() -> bool:
    """
    Checks if the main server executable is present.
    Uses env variable `EXECUTABLE` as path to check.
    """
    executable_path = getenv("EXECUTABLE")
    return os.path.isfile(executable_path)


def generate_moderator_list(mod_list: list) -> str:
    """
    Generates the string required by the server_config.sii file.
    Example:
    ```python
    >>> print(generate_moderator_list(["1028371289", "1247129874"]))
    moderator_list: 2
    moderator_list[0]: 1028371289
    moderator_list[1]: 1247129874
    ```
    """

    ids = []
    for mod in mod_list:
        mod = str(mod).strip()
        if not mod:
            continue
        if not mod.isdigit():
            logging.warning(f"Ignoring invalid moderator steam ID {mod!r}. Only digits are allowed.")
            continue
        ids.append(mod)

    if not ids:
        return "moderator_list: 0"

    out_str = f"moderator_list: {len(ids)}\n"
    for i, mod in enumerate(ids):
        out_str += f" moderator_list[{i}]: {mod}\n"

    return out_str


def sii_escape(value: str) -> str:
    """
    Escapes a value for use inside a double quoted string in a .sii file.
    Backslashes and double quotes are escaped, control characters
    (including newlines) are removed so a value cannot break out of its line.
    """
    value = "".join(ch for ch in str(value) if ch.isprintable())
    return value.replace("\\", "\\\\").replace('"', '\\"')


def get_version():
    with open("/version", "r") as f:
        return f.readline().strip()


def is_truthy(value: str | bool | None) -> bool:
    """
    Returns True if str is "yes", "true", "on" or "1".
    Case insensitive.
    """
    if value is None:
        return False

    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception as e:
            logging.warning("Could not convert value to str", exc_info=True)
            return False

    if value.lower().strip() in {"yes", "true", "on", "1"}:
        return True

    return False


def get_current_max_players(config_ds: str) -> int:
    """
    Returns the value of `g_max_convoy_size` in config_ds.cfg.
    Returns 0 if the file or the setting does not exist.
    """
    if not os.path.isfile(config_ds):
        return 0
    with open(config_ds, "r") as f:
        for line in f:
            if "g_max_convoy_size" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    return int(match.group(1))
    return 0


def max_player_workaround(config_ds: str, max_players: int):
    logging.info("You requested more than 8 players. Trying a workaround to enable this...")
    if max_players > 64:
        logging.warning("!!You requested more than 64 players. This probably wont work!! Warranty is out the window!")

    if not os.path.isfile(config_ds):
        logging.warning("config_ds.cfg does not exist. This is probably since this is the first start.")
        logging.warning("Please restart the container `docker compose restart` to apply player limit workaround.")
        return

    if get_current_max_players(config_ds) == max_players:
        logging.info("Request player count already in config_ds. No changes necessary.")
        return

    os.chmod(config_ds, 0o600)
    try:
        with open(config_ds, "r") as f:
            lines = f.readlines()

        found = False
        for i, line in enumerate(lines):
            if "g_max_convoy_size" in line:
                lines[i] = re.sub(r"\d+", str(max_players), line, count=1)
                found = True

        if not found:
            logging.warning("g_max_convoy_size not found in config_ds.cfg. Player limit workaround not applied.")
            return

        with open(config_ds, "w") as fw:
            fw.writelines(lines)
        logging.info("config_ds.cfg modified and written.")
    finally:
        os.chmod(config_ds, 0o400)


def generate_config() -> str:
    """
    Generates the config file based on environment variables.
    Conforms to SCS scheme (that is sadly not published...).
    """
    print("[INFO]: Writing config file...")

    server_name = getenv("ETS_SERVER_NAME", "Euro Truck Simulator 2 Docker Server")
    description = getenv("ETS_SERVER_DESCRIPTION", "")
    welcome_message = getenv("ETS_SERVER_WELCOME_MESSAGE", "")
    password = getenv("ETS_SERVER_PASSWORD", "")
    max_players = getenv("ETS_SERVER_MAX_PLAYERS", "8")
    max_vehicles_total = getenv("ETS_SERVER_MAX_VEHICLES_TOTAL", "100")
    max_ai_vehicles_player = getenv("ETS_SERVER_MAX_AI_VEHICLES_PLAYER", "50")
    max_ai_vehicles_player_spawn = getenv("ETS_SERVER_MAX_AI_VEHICLES_PLAYER_SPAWN", "50")
    connection_virtual_port = getenv("ETS_SERVER_CONNECTION_VIRTUAL_PORT", "100")
    query_virtual_port = getenv("ETS_SERVER_QUERY_VIRTUAL_PORT", "101")
    server_port = getenv("ETS_SERVER_PORT", "27015")
    query_port = getenv("ETS_SERVER_QUERY_PORT", "27016")
    server_logon_token = getenv("ETS_SERVER_LOGON_TOKEN", "")
    player_damage = is_truthy(getenv("ETS_SERVER_PLAYER_DAMAGE", "true"))
    traffic = is_truthy(getenv("ETS_SERVER_TRAFFIC", "true"))
    hide_in_company = is_truthy(getenv("ETS_SERVER_HIDE_IN_COMPANY", "false"))
    hide_colliding = is_truthy(getenv("ETS_SERVER_HIDE_COLLIDING", "true"))
    force_speedlimiter = is_truthy(getenv("ETS_SERVER_FORCE_SPEEDLIMITER", "false"))
    mods_optioning = is_truthy(getenv("ETS_SERVER_MODS_OPTIONING", "false"))
    timezones = is_truthy(getenv("ETS_SERVER_TIMEZONES", "false"))
    service_no_collision = is_truthy(getenv("ETS_SERVER_SERVICE_NO_COLLISION", "false"))
    in_menu_ghosting = is_truthy(getenv("ETS_SERVER_IN_MENU_GHOSTING", "false"))
    name_tags = is_truthy(getenv("ETS_SERVER_NAME_TAGS", "true"))
    friends_only = is_truthy(getenv("ETS_SERVER_FRIENDS_ONLY", "false"))
    show_server = is_truthy(getenv("ETS_SERVER_SHOW_SERVER", "true"))
    moderator_list = getenv("ETS_SERVER_MODERATORS", "").split(",")
    moderator_list_generated = generate_moderator_list(moderator_list)

# This is ugly AF but if you indent it differently it breaks the config...
    server_config = f"""SiiNunit
{{
server_config : _nameless.44c.eab0 {{
 lobby_name: "{sii_escape(server_name)}"
 description: "{sii_escape(description)}"
 welcome_message: "{sii_escape(welcome_message)}"
 password: "{sii_escape(password)}"
 max_players: {int(max_players)}
 max_vehicles_total: {int(max_vehicles_total)}
 max_ai_vehicles_player: {int(max_ai_vehicles_player)}
 max_ai_vehicles_player_spawn: {int(max_ai_vehicles_player_spawn)}
 connection_virtual_port: {int(connection_virtual_port)}
 query_virtual_port: {int(query_virtual_port)}
 connection_dedicated_port: {int(server_port)}
 query_dedicated_port: {int(query_port)}
 server_logon_token: "{sii_escape(server_logon_token)}"
 player_damage: {str(player_damage).lower()}
 traffic: {str(traffic).lower()}
 hide_in_company: {str(hide_in_company).lower()}
 hide_colliding: {str(hide_colliding).lower()}
 force_speed_limiter: {str(force_speedlimiter).lower()}
 mods_optioning: {str(mods_optioning).lower()}
 timezones: {int(timezones)}
 service_no_collision: {str(service_no_collision).lower()}
 in_menu_ghosting: {str(in_menu_ghosting).lower()}
 name_tags: {str(name_tags).lower()}
 friends_only: {str(friends_only).lower()}
 show_server: {str(show_server).lower()}
 {moderator_list_generated}
}}
}}
"""

    return server_config


if __name__ == "__main__":
    level = logging.INFO
    frmt = "%(asctime)s [%(levelname)s]: %(message)s"
    if getenv("DEBUG") is not None:
        print("Enabling debug")
        level = logging.DEBUG
        frmt = "%(asctime)s [%(levelname)s]: %(message)s [%(funcName)s]"
    logging.basicConfig(stream=sys.stdout, level=level, format=frmt, datefmt="%H:%M:%S", force=True)
    logging.debug("DEBUG MODE ENABLED!")
    print_debug_env()

    logging.info(f"Docker Container Version: {get_version()}")

    write_config = is_truthy(getenv("ETS_SERVER_WRITE_CONFIG", "true"))
    if write_config:
        config = generate_config()
        server_config = getenv("ETS_SERVER_CONFIG_FILE_PATH", "/home/steam/.local/share/Euro Truck Simulator 2/server_config.sii")
        try:
            # Config contains password and logon token: only readable by the server user
            fd = os.open(server_config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(config)
            os.chmod(server_config, 0o600)
            logging.info("Config file written.")
        except OSError as e:
            logging.error(f"Could not write config file ({server_config}): {e}. Check file permissions!")
            exit(1)

    if is_truthy(getenv("ETS_SERVER_UPDATE_ON_START", "true")) or not server_files_exist():
        APP_ID = getenv("APP_ID")
        logging.info(f"Updating {'ETS' if int(APP_ID) == 1948160 else 'ATS'} Server...")
        server_branch = getenv("ETS_SERVER_BRANCH", "public")
        logging.info(f"Branch selected: {server_branch}")

        cmd = [
            "/home/steam/steamcmd/steamcmd.sh",
            "+force_install_dir",
            "/app",
            "+login",
            "anonymous",
            "+app_update",
            str(APP_ID),
            "-beta",
            str(server_branch),
            "validate",
            "+quit"
        ]
        logging.debug(f"SteamCMD command: {' '.join(cmd)}")

        result = subprocess.run(cmd)

        if result.returncode != 0:
            logging.error("Server Update failed!")
            logging.error(f"SteamCMD exited with exit code {result.returncode}")
            exit(result.returncode)

        logging.info("Update done.")
    else:
        logging.warning("Skipping server update. To update set 'ETS_SERVER_UPDATE_ON_START=true'.")

    if write_config:
        max_players = int(getenv("ETS_SERVER_MAX_PLAYERS", 8))
        if max_players > 8:
            config_ds = server_config.replace("server_config.sii", "config_ds.cfg")
            max_player_workaround(config_ds, max_players)
