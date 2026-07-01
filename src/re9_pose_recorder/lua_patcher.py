from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .utils import timestamp_id


BEGIN_MARKER = "-- BEGIN RE9_AESTHETIC_POSE_LOGGER"
END_MARKER = "-- END RE9_AESTHETIC_POSE_LOGGER"


@dataclass(frozen=True)
class LuaPatchStatus:
    lua_path: Path
    exists: bool
    patched: bool
    message: str


def _lua_string(value: str | Path) -> str:
    return str(value).replace("\\", "/").replace('"', '\\"')


def check_lua(config: AppConfig) -> LuaPatchStatus:
    lua_path = config.lua_path
    if not lua_path.exists():
        return LuaPatchStatus(lua_path, False, False, f"Lua file not found: {lua_path}")
    text = _read_text_preserving(lua_path)[0]
    patched = BEGIN_MARKER in text and END_MARKER in text
    return LuaPatchStatus(lua_path, True, patched, "Lua file exists.")


def backup_lua(config: AppConfig) -> Path:
    lua_path = config.lua_path
    if not lua_path.exists():
        raise FileNotFoundError(f"Lua file not found: {lua_path}")
    backup_dir = config.lua_backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"{lua_path.name}.{timestamp_id()}.bak"
    shutil.copy2(lua_path, destination)
    return destination


def verify_lua_patch(config: AppConfig) -> LuaPatchStatus:
    status = check_lua(config)
    if not status.exists:
        return status
    if not status.patched:
        return LuaPatchStatus(status.lua_path, True, False, "Lua logger patch markers are not installed.")
    return LuaPatchStatus(status.lua_path, True, True, "Lua logger patch markers are installed.")


def patch_lua_logger(config: AppConfig) -> tuple[Path, Path]:
    lua_path = config.lua_path
    if not lua_path.exists():
        raise FileNotFoundError(f"Lua file not found: {lua_path}")
    text, newline = _read_text_preserving(lua_path)
    if BEGIN_MARKER not in text and "re.on_" not in text:
        raise RuntimeError("Expected REFramework callback insertion point was not found; refusing to patch.")

    backup_path = backup_lua(config)
    block = build_lua_block(config, newline)
    new_text = _replace_or_append_block(text, block, newline)
    lua_path.write_text(new_text, encoding="utf-8", newline="")
    return lua_path, backup_path


def restore_lua(config: AppConfig, backup: str | Path) -> Path:
    backup_path = Path(backup).expanduser()
    if not backup_path.is_absolute():
        backup_path = Path.cwd() / backup_path
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    lua_path = config.lua_path
    if lua_path.name != "RE9FreeCam.lua":
        raise RuntimeError(f"Configured Lua path does not look like RE9FreeCam.lua: {lua_path}")
    shutil.copy2(backup_path, lua_path)
    return lua_path


def build_lua_block(config: AppConfig, newline: str = "\n") -> str:
    control_name = _lua_string(config.control_file.name)
    status_name = _lua_string(config.status_file.name)
    pose_log_name = _lua_string(config.pose_log_file.name)
    interval = float(config.raw["lua_logger"]["default_interval_sec"])
    lines = [
        BEGIN_MARKER,
        "local re9_pose_logger = re9_pose_logger or {}",
        "-- REFramework Lua may reject absolute paths. json/io paths are relative to reframework/data here.",
        "re9_pose_logger.data_dir = re9_pose_logger.data_dir or \"\"",
        "re9_pose_logger.control_file = re9_pose_logger.control_file or \"" + control_name + "\"",
        "re9_pose_logger.status_file = re9_pose_logger.status_file or \"" + status_name + "\"",
        "re9_pose_logger.pose_log_file = re9_pose_logger.pose_log_file or \"" + pose_log_name + "\"",
        f"re9_pose_logger.interval_sec = re9_pose_logger.interval_sec or {interval:.6f}",
        "re9_pose_logger.enabled = re9_pose_logger.enabled ~= false",
        "re9_pose_logger.logging = re9_pose_logger.logging or false",
        "re9_pose_logger.session_id = re9_pose_logger.session_id or \"\"",
        "re9_pose_logger.rows_written = re9_pose_logger.rows_written or 0",
        "re9_pose_logger.last_error = re9_pose_logger.last_error or \"\"",
        "re9_pose_logger.last_sample_clock = re9_pose_logger.last_sample_clock or 0",
        "re9_pose_logger.last_control_clock = re9_pose_logger.last_control_clock or 0",
        "re9_pose_logger.session_start_clock = re9_pose_logger.session_start_clock or 0",
        "re9_pose_logger.file_handle = re9_pose_logger.file_handle or nil",
        "re9_pose_logger.last_command_id = re9_pose_logger.last_command_id or \"\"",
        "re9_pose_logger.scan_pose_enabled = re9_pose_logger.scan_pose_enabled or false",
        "re9_pose_logger.scan_segment_id = re9_pose_logger.scan_segment_id or \"\"",
        "re9_pose_logger.scan_x = re9_pose_logger.scan_x or 0",
        "re9_pose_logger.scan_y = re9_pose_logger.scan_y or 0",
        "re9_pose_logger.scan_z = re9_pose_logger.scan_z or 0",
        "re9_pose_logger.scan_yaw = re9_pose_logger.scan_yaw or 0",
        "re9_pose_logger.scan_yaw_start = re9_pose_logger.scan_yaw_start or 0",
        "re9_pose_logger.scan_yaw_end = re9_pose_logger.scan_yaw_end or 0",
        "re9_pose_logger.scan_pitch = re9_pose_logger.scan_pitch or 0",
        "re9_pose_logger.scan_fov = re9_pose_logger.scan_fov or nil",
        "re9_pose_logger.scan_start_clock = re9_pose_logger.scan_start_clock or 0",
        "re9_pose_logger.scan_duration_sec = re9_pose_logger.scan_duration_sec or 0",
        "re9_pose_logger.physics_probe_status = re9_pose_logger.physics_probe_status or \"not run\"",
        "re9_pose_logger.physics_probe_contacts = re9_pose_logger.physics_probe_contacts or 0",
        "re9_pose_logger.physics_probe_rays = re9_pose_logger.physics_probe_rays or 0",
        "re9_pose_logger.physics_probe_pose_valid = re9_pose_logger.physics_probe_pose_valid ~= false",
        "re9_pose_logger.physics_probe_details = re9_pose_logger.physics_probe_details or \"\"",
        "re9_pose_logger.physics_probe_error = re9_pose_logger.physics_probe_error or \"\"",
        "re9_pose_logger.physics_clip_distance = re9_pose_logger.physics_clip_distance or 0.03",
        "re9_pose_logger.physics_near_distance = re9_pose_logger.physics_near_distance or 0.12",
        "local re9_pose_is_freecam_mode",
        "",
        "local function re9_pose_escape_json(value)",
        "    value = tostring(value or \"\")",
        "    value = value:gsub('\\\\', '\\\\\\\\'):gsub('\"', '\\\\\"'):gsub('\\n', '\\\\n')",
        "    return value",
        "end",
        "",
        "local function re9_pose_basename(path)",
        "    path = tostring(path or \"\")",
        "    path = path:gsub('\\\\', '/')",
        "    local name = path:match('([^/]+)$') or path",
        "    if name == \"\" then name = \"re9_freecam_pose_log.csv\" end",
        "    return name",
        "end",
        "",
        "local function re9_pose_data_path(name)",
        "    name = re9_pose_basename(name)",
        "    if re9_pose_logger.data_dir == nil or re9_pose_logger.data_dir == \"\" then return name end",
        "    return re9_pose_logger.data_dir .. \"/\" .. name",
        "end",
        "",
        "local function re9_pose_csv_path(path)",
        "    return re9_pose_data_path(re9_pose_basename(path or re9_pose_logger.pose_log_file))",
        "end",
        "",
        "local function re9_pose_write_status()",
        "    local payload = {",
        "        session_id = re9_pose_logger.session_id or \"\",",
        "        logging = re9_pose_logger.logging == true,",
        "        rows_written = re9_pose_logger.rows_written or 0,",
        "        pose_log_file = re9_pose_logger.pose_log_file or \"\",",
        "        scan_pose_enabled = re9_pose_logger.scan_pose_enabled == true,",
        "        scan_segment_id = re9_pose_logger.scan_segment_id or \"\",",
        "        physics_probe_status = re9_pose_logger.physics_probe_status or \"\",",
        "        physics_probe_contacts = re9_pose_logger.physics_probe_contacts or 0,",
        "        physics_probe_rays = re9_pose_logger.physics_probe_rays or 0,",
        "        physics_probe_pose_valid = re9_pose_logger.physics_probe_pose_valid == true,",
        "        physics_probe_details = re9_pose_logger.physics_probe_details or \"\",",
        "        physics_probe_error = re9_pose_logger.physics_probe_error or \"\",",
        "        last_error = re9_pose_logger.last_error or \"\"",
        "    }",
        "    local ok, err = pcall(function()",
        "        if json ~= nil and json.dump_file ~= nil then",
        "            json.dump_file(re9_pose_logger.status_file, payload)",
        "        else",
        "            local f = assert(io.open(re9_pose_data_path(re9_pose_logger.status_file), \"w\"))",
        "            f:write(string.format('{\"session_id\":\"%s\",\"logging\":%s,\"rows_written\":%d,\"pose_log_file\":\"%s\",\"scan_pose_enabled\":%s,\"scan_segment_id\":\"%s\",\"physics_probe_status\":\"%s\",\"physics_probe_contacts\":%d,\"physics_probe_rays\":%d,\"physics_probe_pose_valid\":%s,\"physics_probe_details\":\"%s\",\"physics_probe_error\":\"%s\",\"last_error\":\"%s\"}',",
        "                re9_pose_escape_json(payload.session_id), tostring(payload.logging), tonumber(payload.rows_written) or 0,",
        "                re9_pose_escape_json(payload.pose_log_file), tostring(payload.scan_pose_enabled), re9_pose_escape_json(payload.scan_segment_id),",
        "                re9_pose_escape_json(payload.physics_probe_status), tonumber(payload.physics_probe_contacts) or 0, tonumber(payload.physics_probe_rays) or 0,",
        "                tostring(payload.physics_probe_pose_valid), re9_pose_escape_json(payload.physics_probe_details),",
        "                re9_pose_escape_json(payload.physics_probe_error), re9_pose_escape_json(payload.last_error)))",
        "            f:close()",
        "        end",
        "    end)",
        "    if not ok then re9_pose_logger.last_error = tostring(err) end",
        "end",
        "",
        "local function re9_pose_read_control()",
        "    local ok, data = pcall(function()",
        "        if json ~= nil and json.load_file ~= nil then return json.load_file(re9_pose_logger.control_file) end",
        "        local f = io.open(re9_pose_data_path(re9_pose_logger.control_file), \"r\")",
        "        if f == nil then return nil end",
        "        local text = f:read(\"*a\")",
        "        f:close()",
        "        if text == nil then return nil end",
        "        return {",
        "            command = text:match('\"command\"%s*:%s*\"([^\"]+)\"'),",
        "            command_id = text:match('\"command_id\"%s*:%s*\"([^\"]+)\"'),",
        "            session_id = text:match('\"session_id\"%s*:%s*\"([^\"]+)\"'),",
        "            pose_log_file = text:match('\"pose_log_file\"%s*:%s*\"([^\"]+)\"'),",
        "            interval_sec = tonumber(text:match('\"interval_sec\"%s*:%s*([%-%d%.]+)')),",
        "            x = tonumber(text:match('\"x\"%s*:%s*([%-%d%.]+)')),",
        "            y = tonumber(text:match('\"y\"%s*:%s*([%-%d%.]+)')),",
        "            z = tonumber(text:match('\"z\"%s*:%s*([%-%d%.]+)')),",
        "            yaw = tonumber(text:match('\"yaw\"%s*:%s*([%-%d%.]+)')),",
        "            yaw_end = tonumber(text:match('\"yaw_end\"%s*:%s*([%-%d%.]+)')),",
        "            duration_sec = tonumber(text:match('\"duration_sec\"%s*:%s*([%-%d%.]+)')),",
        "            pitch = tonumber(text:match('\"pitch\"%s*:%s*([%-%d%.]+)')),",
        "            fov = tonumber(text:match('\"fov\"%s*:%s*([%-%d%.]+)')),",
        "            segment_id = text:match('\"segment_id\"%s*:%s*\"([^\"]+)\"')",
        "        }",
        "    end)",
        "    if ok then return data end",
        "    re9_pose_logger.last_error = tostring(data)",
        "    return nil",
        "end",
        "",
        "local function re9_pose_vec3(x, y, z)",
        "    if Vector3f ~= nil and Vector3f.new ~= nil then return Vector3f.new(x, y, z) end",
        "    return { x = x, y = y, z = z }",
        "end",
        "",
        "local function re9_pose_call_query(query, method_name, ...)",
        "    if query == nil or query.call == nil then return false, \"query has no call method\" end",
        "    local ok, result = pcall(function(...) return query:call(method_name, ...) end, ...)",
        "    if ok then return true, result end",
        "    return false, tostring(result)",
        "end",
        "",
        "local function re9_pose_contact_min_distance(result, count)",
        "    local min_distance = nil",
        "    local max_index = (tonumber(count) or 0) - 1",
        "    if max_index > 7 then max_index = 7 end",
        "    for i = 0, max_index do",
        "        local ok_cp, cp = pcall(function() return result:call(\"getContactPoint\", i) end)",
        "        if ok_cp and cp ~= nil then",
        "            local d = nil",
        "            if type(cp) == \"table\" then d = tonumber(cp.Distance or cp.distance) end",
        "            if d == nil then pcall(function() d = tonumber(cp:get_field(\"Distance\")) end) end",
        "            if d == nil then pcall(function() d = tonumber(cp:call(\"get_Distance\")) end) end",
        "            if d ~= nil and (min_distance == nil or d < min_distance) then min_distance = d end",
        "        end",
        "    end",
        "    return min_distance",
        "end",
        "",
        "local function re9_pose_run_single_cast_ray(origin, target, inside_hits)",
        "    if sdk == nil then return false, \"sdk unavailable\", 0 end",
        "    local physics_type = sdk.find_type_definition(\"via.physics.System\")",
        "    if physics_type == nil then return false, \"via.physics.System type not found\", 0 end",
        "    local query = sdk.create_instance(\"via.physics.CastRayQuery\")",
        "    if query == nil then query = sdk.create_instance(\"via.physics.CastRayQuery\", true) end",
        "    if query == nil then return false, \"could not create CastRayQuery\", 0 end",
        "    re9_pose_call_query(query, \"clearOptions\")",
        "    re9_pose_call_query(query, \"enableAllHits\")",
        "    re9_pose_call_query(query, \"enableOneHitBreak\")",
        "    if inside_hits then re9_pose_call_query(query, \"enableInsideHits\") end",
        "    local ok_set, set_err = re9_pose_call_query(query, \"setRay(via.vec3, via.vec3)\", origin, target)",
        "    if not ok_set then ok_set, set_err = re9_pose_call_query(query, \"setRay\", origin, target) end",
        "    if not ok_set then return false, \"setRay failed: \" .. tostring(set_err), 0 end",
        "    local ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, \"castRay(via.physics.CastRayQuery)\", query) end)",
        "    if not ok_cast then ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, \"castRay\", query) end) end",
        "    if not ok_cast or result == nil then return false, \"castRay failed: \" .. tostring(result), 0 end",
        "    local ok_num, num = pcall(function() return result:call(\"get_NumContactPoints\") end)",
        "    if not ok_num then ok_num, num = pcall(function() return result:call(\"get_NumContactPoints()\") end) end",
        "    if not ok_num then return false, \"get_NumContactPoints failed: \" .. tostring(num), 0 end",
        "    num = tonumber(num) or 0",
        "    return true, \"api_ok\", num, re9_pose_contact_min_distance(result, num)",
        "end",
        "",
        "local function re9_pose_run_physics_probe()",
        "    if not re9_pose_is_freecam_mode() or freecam_pos == nil then",
        "        re9_pose_logger.physics_probe_status = \"freecam disabled\"",
        "        re9_pose_logger.physics_probe_error = \"Enable FreeCam before physics probe\"",
        "        re9_pose_write_status()",
        "        return",
        "    end",
        "    local x = tonumber(freecam_pos.x) or 0",
        "    local y = tonumber(freecam_pos.y) or 0",
        "    local z = tonumber(freecam_pos.z) or 0",
        "    local origin = re9_pose_vec3(x, y, z)",
        "    local d = 0.35",
        "    local targets = {",
        "        {\"+x\", re9_pose_vec3(x + d, y, z)}, {\"-x\", re9_pose_vec3(x - d, y, z)},",
        "        {\"+y\", re9_pose_vec3(x, y + d, z)}, {\"-y\", re9_pose_vec3(x, y - d, z)},",
        "        {\"+z\", re9_pose_vec3(x, y, z + d)}, {\"-z\", re9_pose_vec3(x, y, z - d)}",
        "    }",
        "    local contacts = 0",
        "    local inside_contacts = 0",
        "    local min_probe_distance = nil",
        "    local near_zero_dirs = 0",
        "    local rays = 0",
        "    local errors = {}",
        "    local detail_parts = {}",
        "    for _, item in ipairs(targets) do",
        "        local label = item[1]",
        "        local target = item[2]",
        "        local ok_a, msg_a, count_a, dist_a = re9_pose_run_single_cast_ray(origin, target, false)",
        "        local ok_i, msg_i, count_i, dist_i = re9_pose_run_single_cast_ray(origin, target, true)",
        "        rays = rays + 2",
        "        if ok_a then contacts = contacts + (tonumber(count_a) or 0) else table.insert(errors, label .. \":normal:\" .. tostring(msg_a)) end",
        "        if ok_i then inside_contacts = inside_contacts + (tonumber(count_i) or 0) else table.insert(errors, label .. \":inside:\" .. tostring(msg_i)) end",
        "        local best_dist = dist_i or dist_a",
        "        if best_dist ~= nil and (min_probe_distance == nil or best_dist < min_probe_distance) then min_probe_distance = best_dist end",
        "        if best_dist ~= nil and best_dist <= 0.02 then near_zero_dirs = near_zero_dirs + 1 end",
        "        table.insert(detail_parts, string.format(\"%s n=%s i=%s d=%s\", label, tostring(count_a or \"?\"), tostring(count_i or \"?\"), best_dist ~= nil and string.format(\"%.4f\", best_dist) or \"?\"))",
        "    end",
        "    re9_pose_logger.physics_probe_contacts = contacts + inside_contacts",
        "    re9_pose_logger.physics_probe_rays = rays",
        "    re9_pose_logger.physics_probe_details = table.concat(detail_parts, \"; \")",
        "    local clip_distance = tonumber(re9_pose_logger.physics_clip_distance) or 0.03",
        "    local near_distance = tonumber(re9_pose_logger.physics_near_distance) or 0.12",
        "    local suspect = near_zero_dirs >= 2 or (min_probe_distance ~= nil and min_probe_distance <= clip_distance)",
        "    re9_pose_logger.physics_probe_pose_valid = not suspect",
        "    if #errors > 0 then",
        "        re9_pose_logger.physics_probe_status = \"error\"",
        "        re9_pose_logger.physics_probe_error = table.concat(errors, \" | \")",
        "    elseif suspect then",
        "        re9_pose_logger.physics_probe_status = \"suspect_clip\"",
        "        re9_pose_logger.physics_probe_error = \"near_zero_dirs=\" .. tostring(near_zero_dirs) .. \" min_distance=\" .. tostring(min_probe_distance or \"?\") .. \" clip_distance=\" .. tostring(clip_distance) .. \" inside_contacts=\" .. tostring(inside_contacts)",
        "    elseif min_probe_distance ~= nil and min_probe_distance < near_distance then",
        "        re9_pose_logger.physics_probe_status = \"near_surface\"",
        "        re9_pose_logger.physics_probe_error = \"min_distance=\" .. tostring(min_probe_distance) .. \" near_distance=\" .. tostring(near_distance) .. \" inside_contacts=\" .. tostring(inside_contacts)",
        "    else",
        "        re9_pose_logger.physics_probe_status = \"api_ok_clear\"",
        "        re9_pose_logger.physics_probe_error = \"\"",
        "    end",
        "    re9_pose_write_status()",
        "end",
        "",
        "local function re9_pose_start(session_id, pose_log_file, interval_sec)",
        "    if io == nil or io.open == nil then",
        "        re9_pose_logger.last_error = \"io.open unavailable in this REFramework Lua environment\"",
        "        re9_pose_write_status()",
        "        return",
        "    end",
        "    if re9_pose_logger.file_handle ~= nil then pcall(function() re9_pose_logger.file_handle:close() end) end",
        "    re9_pose_logger.session_id = session_id or os.date(\"%Y%m%d_%H%M%S\")",
        "    re9_pose_logger.pose_log_file = re9_pose_csv_path(pose_log_file or re9_pose_logger.pose_log_file)",
        "    re9_pose_logger.interval_sec = tonumber(interval_sec) or re9_pose_logger.interval_sec",
        "    re9_pose_logger.rows_written = 0",
        "    re9_pose_logger.session_start_clock = os.clock()",
        "    re9_pose_logger.last_sample_clock = 0",
        "    re9_pose_logger.last_error = \"\"",
        "    local ok, result = pcall(function() return io.open(re9_pose_logger.pose_log_file, \"w\") end)",
        "    if not ok or result == nil then",
        "        re9_pose_logger.logging = false",
        "        re9_pose_logger.last_error = \"Could not open pose log file: \" .. tostring(result)",
        "        re9_pose_write_status()",
        "        return",
        "    end",
        "    re9_pose_logger.file_handle = result",
        "    re9_pose_logger.file_handle:write(\"session_id,timestamp_sec,x,y,z,yaw,yaw_norm_rad,yaw_norm_deg,pitch,fov,freecam_mode,user_has_rotated\\n\")",
        "    re9_pose_logger.logging = true",
        "    re9_pose_write_status()",
        "end",
        "",
        "local function re9_pose_stop()",
        "    re9_pose_logger.logging = false",
        "    re9_pose_logger.scan_pose_enabled = false",
        "    re9_pose_logger.scan_segment_id = \"\"",
        "    if re9_pose_logger.file_handle ~= nil then",
        "        pcall(function() re9_pose_logger.file_handle:flush(); re9_pose_logger.file_handle:close() end)",
        "        re9_pose_logger.file_handle = nil",
        "    end",
        "    re9_pose_write_status()",
        "end",
        "",
        "local function re9_pose_set_scan_pose(control)",
        "    if control == nil then return end",
        "    if not re9_pose_is_freecam_mode() or freecam_pos == nil then",
        "        re9_pose_logger.last_error = \"Enable FreeCam before running scan set_pose\"",
        "        re9_pose_write_status()",
        "        return",
        "    end",
        "    re9_pose_logger.scan_pose_enabled = true",
        "    re9_pose_logger.scan_segment_id = tostring(control.segment_id or \"\")",
        "    re9_pose_logger.scan_x = tonumber(control.x) or re9_pose_logger.scan_x",
        "    re9_pose_logger.scan_y = tonumber(control.y) or re9_pose_logger.scan_y",
        "    re9_pose_logger.scan_z = tonumber(control.z) or re9_pose_logger.scan_z",
        "    re9_pose_logger.scan_yaw = tonumber(control.yaw) or re9_pose_logger.scan_yaw",
        "    re9_pose_logger.scan_yaw_start = re9_pose_logger.scan_yaw",
        "    re9_pose_logger.scan_yaw_end = tonumber(control.yaw_end) or re9_pose_logger.scan_yaw",
        "    re9_pose_logger.scan_pitch = tonumber(control.pitch) or re9_pose_logger.scan_pitch",
        "    re9_pose_logger.scan_duration_sec = tonumber(control.duration_sec) or 0",
        "    re9_pose_logger.scan_start_clock = os.clock()",
        "    if control.fov ~= nil then re9_pose_logger.scan_fov = tonumber(control.fov) end",
        "    re9_pose_logger.last_error = \"\"",
        "    re9_pose_write_status()",
        "end",
        "",
        "local function re9_pose_clear_scan_pose()",
        "    re9_pose_logger.scan_pose_enabled = false",
        "    re9_pose_logger.scan_segment_id = \"\"",
        "    re9_pose_write_status()",
        "end",
        "",
        "local function re9_pose_apply_scan_pose()",
        "    if not re9_pose_logger.scan_pose_enabled then return end",
        "    if not re9_pose_is_freecam_mode() or freecam_pos == nil then return end",
        "    freecam_pos.x = re9_pose_logger.scan_x",
        "    freecam_pos.y = re9_pose_logger.scan_y",
        "    freecam_pos.z = re9_pose_logger.scan_z",
        "    local yaw_value = re9_pose_logger.scan_yaw",
        "    if re9_pose_logger.scan_duration_sec ~= nil and re9_pose_logger.scan_duration_sec > 0 then",
        "        local t = (os.clock() - re9_pose_logger.scan_start_clock) / re9_pose_logger.scan_duration_sec",
        "        if t < 0 then t = 0 end",
        "        if t > 1 then t = 1 end",
        "        yaw_value = re9_pose_logger.scan_yaw_start + (re9_pose_logger.scan_yaw_end - re9_pose_logger.scan_yaw_start) * t",
        "    end",
        "    re9_pose_logger.scan_yaw = yaw_value",
        "    freecam_yaw = yaw_value",
        "    freecam_pitch = re9_pose_logger.scan_pitch",
        "    if re9_pose_logger.scan_fov ~= nil then global_fov = re9_pose_logger.scan_fov; use_custom_fov = true end",
        "    user_has_rotated = true",
        "    yaw_pitch_initialized = true",
        "end",
        "",
        "local function re9_pose_write_scan_camera()",
        "    if not re9_pose_logger.scan_pose_enabled then return end",
        "    if not re9_pose_is_freecam_mode() or freecam_pos == nil then return end",
        "    re9_pose_apply_scan_pose()",
        "    if type(write_yawpitch_matrix) == \"function\" then",
        "        pcall(function() write_yawpitch_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z, freecam_yaw, freecam_pitch) end)",
        "    end",
        "end",
        "",
        "local function re9_pose_get_number(name, fallback)",
        "    local value = _G[name]",
        "    if type(value) == \"number\" then return value end",
        "    return fallback or 0",
        "end",
        "",
        "local function re9_pose_get_pose()",
        "    local pos = nil",
        "    if type(freecam_pos) ~= \"nil\" then pos = freecam_pos end",
        "    if pos == nil and type(camera_pos) ~= \"nil\" then pos = camera_pos end",
        "    if pos == nil then return nil end",
        "    local x = pos.x or pos[1] or 0",
        "    local y = pos.y or pos[2] or 0",
        "    local z = pos.z or pos[3] or 0",
        "    local yaw_value = 0",
        "    local pitch_value = 0",
        "    local fov_value = 0",
        "    if type(freecam_yaw) ~= \"nil\" then yaw_value = freecam_yaw elseif type(yaw) ~= \"nil\" then yaw_value = yaw else yaw_value = re9_pose_get_number(\"yaw\", 0) end",
        "    if type(freecam_pitch) ~= \"nil\" then pitch_value = freecam_pitch elseif type(pitch) ~= \"nil\" then pitch_value = pitch else pitch_value = re9_pose_get_number(\"pitch\", 0) end",
        "    if type(global_fov) ~= \"nil\" then fov_value = global_fov elseif type(fov) ~= \"nil\" then fov_value = fov else fov_value = re9_pose_get_number(\"fov\", 0) end",
        "    return x, y, z, yaw_value, pitch_value, fov_value",
        "end",
        "",
        "function re9_pose_is_freecam_mode()",
        "    if type(freecam_mode) ~= \"nil\" then return freecam_mode == true end",
        "    if type(is_freecam) ~= \"nil\" then return is_freecam == true end",
        "    if type(enabled) ~= \"nil\" then return enabled == true end",
        "    return false",
        "end",
        "",
        "local function re9_pose_log_sample()",
        "    if not re9_pose_logger.enabled or not re9_pose_logger.logging then return end",
        "    if not re9_pose_is_freecam_mode() then return end",
        "    local x, y, z, yaw_value, pitch_value, fov_value = re9_pose_get_pose()",
        "    if x == nil then return end",
        "    local now = os.clock()",
        "    if re9_pose_logger.last_sample_clock ~= 0 and (now - re9_pose_logger.last_sample_clock) < re9_pose_logger.interval_sec then return end",
        "    re9_pose_logger.last_sample_clock = now",
        "    local timestamp_sec = now - re9_pose_logger.session_start_clock",
        "    local rotated = false",
        "    if type(user_has_rotated) ~= \"nil\" then rotated = user_has_rotated == true end",
        "    local yaw_norm_rad = yaw_value % (math.pi * 2)",
        "    if yaw_norm_rad < 0 then yaw_norm_rad = yaw_norm_rad + (math.pi * 2) end",
        "    local yaw_norm_deg = math.deg(yaw_norm_rad)",
        "    local ok, err = pcall(function()",
        "        re9_pose_logger.file_handle:write(string.format(\"%s,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.6f,%.9f,%.9f,%s,%s\\n\",",
        "            re9_pose_logger.session_id, timestamp_sec, x, y, z, yaw_value, yaw_norm_rad, yaw_norm_deg, pitch_value, fov_value,",
        "            tostring(re9_pose_is_freecam_mode()), tostring(rotated)))",
        "        re9_pose_logger.rows_written = re9_pose_logger.rows_written + 1",
        "        if re9_pose_logger.rows_written % 30 == 0 then re9_pose_logger.file_handle:flush(); re9_pose_write_status() end",
        "    end)",
        "    if not ok then re9_pose_logger.last_error = tostring(err); re9_pose_write_status() end",
        "end",
        "",
        "local function re9_pose_poll_control()",
        "    local now = os.clock()",
        "    if (now - re9_pose_logger.last_control_clock) < 0.25 then return end",
        "    re9_pose_logger.last_control_clock = now",
        "    local control = re9_pose_read_control()",
        "    if control == nil or control.command == nil then return end",
        "    local command_id = tostring(control.command_id or control.command or \"\")",
        "    if command_id ~= \"\" and command_id == re9_pose_logger.last_command_id then return end",
        "    re9_pose_logger.last_command_id = command_id",
        "    if control.command == \"start\" and control.session_id ~= re9_pose_logger.session_id then",
        "        re9_pose_start(control.session_id, control.pose_log_file, control.interval_sec)",
        "    elseif control.command == \"stop\" and control.session_id == re9_pose_logger.session_id then",
        "        re9_pose_stop()",
        "    elseif control.command == \"set_pose\" then",
        "        re9_pose_set_scan_pose(control)",
        "    elseif control.command == \"clear_pose\" then",
        "        re9_pose_clear_scan_pose()",
        "    elseif control.command == \"physics_probe\" then",
        "        re9_pose_run_physics_probe()",
        "    end",
        "end",
        "",
        "re.on_pre_application_entry(\"LateUpdateBehavior\", function()",
        "    pcall(re9_pose_apply_scan_pose)",
        "end)",
        "",
        "re.on_pre_application_entry(\"LockScene\", function()",
        "    pcall(re9_pose_write_scan_camera)",
        "end)",
        "",
        "re.on_frame(function()",
        "    pcall(re9_pose_poll_control)",
        "    pcall(re9_pose_apply_scan_pose)",
        "    pcall(re9_pose_log_sample)",
        "end)",
        "",
        "re.on_draw_ui(function()",
        "    if imgui.tree_node(\"RE9 Aesthetic Pose Logger\") then",
        "        changed, re9_pose_logger.enabled = imgui.checkbox(\"Pose Logging Enabled\", re9_pose_logger.enabled)",
        "        changed, re9_pose_logger.interval_sec = imgui.slider_float(\"Logging Interval\", re9_pose_logger.interval_sec, 0.005, 1.0)",
        "        if imgui.button(\"Start Pose Log\") then re9_pose_start(os.date(\"%Y%m%d_%H%M%S\"), re9_pose_logger.pose_log_file, re9_pose_logger.interval_sec) end",
        "        imgui.same_line()",
        "        if imgui.button(\"Stop Pose Log\") then re9_pose_stop() end",
        "        imgui.text(\"Logger status: \" .. tostring(re9_pose_logger.logging))",
        "        imgui.text(\"Session id: \" .. tostring(re9_pose_logger.session_id))",
        "        imgui.text(\"Rows written: \" .. tostring(re9_pose_logger.rows_written))",
        "        imgui.text(\"Pose log file: \" .. tostring(re9_pose_logger.pose_log_file))",
        "        imgui.text(\"Scan pose enabled: \" .. tostring(re9_pose_logger.scan_pose_enabled))",
        "        imgui.text(\"Scan segment id: \" .. tostring(re9_pose_logger.scan_segment_id))",
        "        changed, re9_pose_logger.physics_clip_distance = imgui.slider_float(\"Physics Clip Distance\", re9_pose_logger.physics_clip_distance, 0.005, 0.2)",
        "        changed, re9_pose_logger.physics_near_distance = imgui.slider_float(\"Physics Near Distance\", re9_pose_logger.physics_near_distance, 0.02, 0.5)",
        "        if imgui.button(\"Test Physics Probe\") then re9_pose_run_physics_probe() end",
        "        imgui.text(\"Physics probe: \" .. tostring(re9_pose_logger.physics_probe_status) .. \" valid=\" .. tostring(re9_pose_logger.physics_probe_pose_valid) .. \" contacts=\" .. tostring(re9_pose_logger.physics_probe_contacts) .. \"/\" .. tostring(re9_pose_logger.physics_probe_rays))",
        "        if re9_pose_logger.physics_probe_details ~= \"\" then imgui.text(\"Physics details: \" .. tostring(re9_pose_logger.physics_probe_details)) end",
        "        if re9_pose_logger.physics_probe_error ~= \"\" then imgui.text(\"Physics error: \" .. tostring(re9_pose_logger.physics_probe_error)) end",
        "        if re9_pose_logger.last_error ~= \"\" then imgui.text(\"Last error: \" .. tostring(re9_pose_logger.last_error)) end",
        "        imgui.tree_pop()",
        "    end",
        "end)",
        END_MARKER,
    ]
    return newline.join(lines) + newline


def _replace_or_append_block(text: str, block: str, newline: str) -> str:
    if BEGIN_MARKER in text or END_MARKER in text:
        start = text.find(BEGIN_MARKER)
        end = text.find(END_MARKER)
        if start == -1 or end == -1 or end < start:
            raise RuntimeError("Lua patch markers are malformed; restore from backup or repair markers before patching.")
        end += len(END_MARKER)
        while end < len(text) and text[end] in "\r\n":
            end += 1
        return text[:start] + block + text[end:]
    spacer = "" if text.endswith(("\n", "\r")) else newline
    return text + spacer + newline + block


def _read_text_preserving(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    newline = "\r\n" if crlf >= lf else "\n"
    return text, newline
