-- RE9 FreeCam — Full: WASD + Mouse Look + Frozen Matrix
-- At activation: captures the ENTIRE 4x4 matrix (rotation+position)
-- Replays captured rotation every frame to freeze the camera view
-- Only position changes with WASD; rotation changes with mouse/Q/E

local freecam_mode = false
local freecam_pos = nil
local freecam_yaw = 0
local freecam_pitch = 0
local prev_mouse_x = nil
local prev_mouse_y = nil
local status_msg = "Listo."
local cam_system_hooked = false
local cam_blocked = false
local hook_call_count = 0
local lockscene_write_count = 0
local joint_buf_write_count = 0
local mouse_ok = false
local log_msgs = {}

-- Experimental Global FOV Configuration
local use_custom_fov = false
local global_fov = 90.0
local original_fov = nil

-- Depth of Field Override
local disable_dof = false

local user_has_rotated = false
local yaw_pitch_initialized = false  -- Have we extracted yaw/pitch from captured matrix?
-- Captured rotation matrix (rows 0-2, 12 floats)
local captured_matrix = nil  -- {r00,r01,r02,r03, r10,r11,r12,r13, r20,r21,r22,r23}

local move_speed = 0.020
local fast_multiplier = 4.0
local mouse_sensitivity = 0.003

-- Configurable Look Keys
local look_key_names = {
    "Right Click (RMB)",
    "Left Click (LMB)",
    "Middle Click (MMB)",
    "Side Button 1 (Mouse 4)",
    "Side Button 2 (Mouse 5)"
}
local look_key_vks = { 0x02, 0x01, 0x04, 0x05, 0x06 }
local look_key_index = 1 -- Default to RMB

-- Toggle Key Configuration
local toggle_vk = 0x72 -- Default to F3
local waiting_for_toggle_key = false

-- Freeze Player Hotkey
local freeze_hotkey_vk = 0x70 -- Default to F1
local waiting_for_freeze_key = false
local prev_freeze_hotkey_down = false

-- Load Config
local config_file = "RE9_FreeCam_Config.json"
local config = json and json.load_file(config_file) or {}

local function save_config()
    config.toggle_vk = toggle_vk
    config.freeze_player = freeze_player
    config.move_speed = move_speed
    config.mouse_sensitivity = mouse_sensitivity
    config.look_key_index = look_key_index
    config.use_custom_fov = use_custom_fov
    config.global_fov = global_fov
    config.disable_dof = disable_dof
    config.freeze_hotkey_vk = freeze_hotkey_vk
    if json then json.dump_file(config_file, config) end
end

if config.toggle_vk then toggle_vk = config.toggle_vk end
if config.move_speed then move_speed = config.move_speed end
if config.mouse_sensitivity then mouse_sensitivity = config.mouse_sensitivity end
if config.look_key_index then look_key_index = config.look_key_index end
if config.use_custom_fov ~= nil then use_custom_fov = config.use_custom_fov end
if config.global_fov then global_fov = config.global_fov end
if config.disable_dof ~= nil then disable_dof = config.disable_dof end
if config.freeze_hotkey_vk then freeze_hotkey_vk = config.freeze_hotkey_vk end

-- Freeze Player Override
local freeze_player = config.freeze_player
if freeze_player == nil then freeze_player = true end

local VK_W = 0x57; local VK_A = 0x41; local VK_S = 0x53; local VK_D = 0x44
local VK_SPACE = 0x20; local VK_CTRL = 0x11; local VK_SHIFT = 0x10
local VK_RBUTTON = 0x02; local VK_Q = 0x51; local VK_E = 0x45
local prev_toggle_down = false

local function get_vk_name(vk)
    local names = {
        [8]="Bksp", [9]="Tab", [13]="Enter", [16]="Shift", [17]="Ctrl", [18]="Alt",
        [20]="Caps", [27]="Esc", [32]="Space", [33]="PgUp", [34]="PgDn",
        [35]="End", [36]="Home", [37]="Left", [38]="Up", [39]="Right", [40]="Down",
        [45]="Ins", [46]="Del"
    }
    if names[vk] then return names[vk] end
    if vk >= 48 and vk <= 57 then return string.char(vk) end
    if vk >= 65 and vk <= 90 then return string.char(vk) end
    if vk >= 112 and vk <= 123 then return "F" .. tostring(vk - 111) end
    return "Key " .. tostring(vk)
end

local function get_main_view()
    local sm = sdk.get_native_singleton("via.SceneManager")
    if not sm then return nil end
    return sdk.call_native_func(sm, sdk.find_type_definition("via.SceneManager"), "get_MainView")
end

local function get_primary_camera()
    local view = get_main_view()
    if not view then return nil end
    return view:call("get_PrimaryCamera")
end

local function get_camera_go_and_transform()
    local cam = get_primary_camera()
    if not cam then return nil, nil end
    local go = cam:call("get_GameObject")
    if not go then return nil, nil end
    return go, go:call("get_Transform")
end

local function get_real_camera_pos()
    local _, trans = get_camera_go_and_transform()
    if not trans then return nil end
    local pos = nil
    pcall(function()
        local joints = trans:call("get_Joints")
        if joints and joints:call("get_Count") > 0 then
            local j0 = joints:call("get_Item", 0)
            local p = j0 and j0:call("get_Position")
            if p then pos = { x = p.x, y = p.y, z = p.z } end
        end
    end)
    if not pos then
        pcall(function()
            local p = trans:call("get_Position")
            if p then pos = { x = p.x, y = p.y, z = p.z } end
        end)
    end
    return pos
end

local function get_player_updater()
    local chr_man = sdk.get_managed_singleton("app.CharacterManager")
    if not chr_man then return nil end
    local ctx = chr_man:get_field("<PlayerContextFast>k__BackingField")
    if not ctx then return nil end
    local go = ctx:call("get_GameObject")
    if not go then return nil end
    local getComp = sdk.find_type_definition("via.GameObject"):get_method("getComponent(System.Type)")
    if not getComp then return nil end
    
    local updater = nil
    local type_a000 = pcall(sdk.typeof, "app.Cp_A000Updater") and sdk.typeof("app.Cp_A000Updater") or nil
    if type_a000 then
        local success, result = pcall(function() return getComp:call(go, type_a000) end)
        if success then updater = result end
    end
    
    if not updater then
        local type_a010 = pcall(sdk.typeof, "app.Cp_A010Updater") and sdk.typeof("app.Cp_A010Updater") or nil
        if type_a010 then
            local success, result = pcall(function() return getComp:call(go, type_a010) end)
            if success then updater = result end
        end
    end
    
    if not updater then
        local type_a100 = pcall(sdk.typeof, "app.Cp_A100Updater") and sdk.typeof("app.Cp_A100Updater") or nil
        if type_a100 then
            local success, result = pcall(function() return getComp:call(go, type_a100) end)
            if success then updater = result end
        end
    end
    
    return updater
end

-- Capture the FULL 4x4 matrix from joint buffer at activation
local function capture_current_matrix()
    local _, trans = get_camera_go_and_transform()
    if not trans then return nil end
    local mat = nil
    -- Read from joint buffer (this is what rendering uses)
    pcall(function()
        local ptr1 = trans:read_qword(0x68)
        if ptr1 and ptr1 > 0x10000 and ptr1 < 0x7FFFFFFFFFFF then
            local buf = sdk.to_managed_object(ptr1)
            if buf then
                mat = {}
                for i = 0, 15 do
                    mat[i+1] = buf:read_float(0x80 + i * 4)
                end
            end
        end
    end)
    -- Fallback: read from Transform worldTransform
    if not mat then
        pcall(function()
            mat = {}
            for i = 0, 15 do
                mat[i+1] = trans:read_float(0x80 + i * 4)
            end
        end)
    end
    return mat
end

-- Write captured rotation + our position to all targets
local function write_frozen_matrix(x, y, z)
    if not captured_matrix then return end
    local _, trans = get_camera_go_and_transform()
    if not trans then return end
    local m = captured_matrix
    
    local function write_to_target(target, base)
        -- Rows 0-2: captured rotation
        for i = 0, 11 do
            target:write_float(base + i * 4, m[i+1])
        end
        -- Row 3: our position
        target:write_float(base + 0x30, x)
        target:write_float(base + 0x34, y)
        target:write_float(base + 0x38, z)
        target:write_float(base + 0x3C, 1)
    end
    
    pcall(function()
        write_to_target(trans, 0x80)
        trans:write_float(0x30, x); trans:write_float(0x34, y); trans:write_float(0x38, z)
    end)
    pcall(function()
        local ptr1 = trans:read_qword(0x68)
        if ptr1 and ptr1 > 0x10000 and ptr1 < 0x7FFFFFFFFFFF then
            local buf = sdk.to_managed_object(ptr1)
            if buf then
                write_to_target(buf, 0x80)
                joint_buf_write_count = joint_buf_write_count + 1
            end
        end
    end)
end

-- Write rotation from yaw/pitch + our position
local function write_yawpitch_matrix(x, y, z, yaw, pitch)
    local _, trans = get_camera_go_and_transform()
    if not trans then return end
    local cy = math.cos(yaw); local sy = math.sin(yaw)
    local cp = math.cos(pitch); local sp = math.sin(pitch)
    
    local function write_to_target(target, base)
        target:write_float(base+0x00, cy);    target:write_float(base+0x04, 0);   target:write_float(base+0x08, -sy);  target:write_float(base+0x0C, 0)
        target:write_float(base+0x10, sy*sp); target:write_float(base+0x14, cp);  target:write_float(base+0x18, cy*sp);target:write_float(base+0x1C, 0)
        target:write_float(base+0x20, sy*cp); target:write_float(base+0x24, -sp); target:write_float(base+0x28, cy*cp);target:write_float(base+0x2C, 0)
        target:write_float(base+0x30, x);     target:write_float(base+0x34, y);   target:write_float(base+0x38, z);    target:write_float(base+0x3C, 1)
    end
    
    pcall(function()
        write_to_target(trans, 0x80)
        trans:write_float(0x30, x); trans:write_float(0x34, y); trans:write_float(0x38, z)
    end)
    pcall(function()
        local ptr1 = trans:read_qword(0x68)
        if ptr1 and ptr1 > 0x10000 and ptr1 < 0x7FFFFFFFFFFF then
            local buf = sdk.to_managed_object(ptr1)
            if buf then
                write_to_target(buf, 0x80)
                joint_buf_write_count = joint_buf_write_count + 1
            end
        end
    end)
end

-- Hook systems
local function install_hooks()
    log_msgs = {}
    if cs then
        local on_update = cs:get_method("onUpdate")
        if on_update then
            pcall(function()
                sdk.hook(on_update,
                    function(args) if cam_blocked then return sdk.PreHookResult.SKIP_ORIGINAL end; return sdk.PreHookResult.CALL_ORIGINAL end,
                    function(retval) return retval end)
                cam_system_hooked = true
            end)
        end
    end
    for _, name in ipairs({"app.EventCameraController", "app.CameraBlender", "app.CameraDirector", "app.CutsceneManager", "via.motion.MotionManager"}) do
        local t = sdk.find_type_definition(name)
        if t then
            for _, m in ipairs(t:get_methods()) do
                local mn = m:get_name()
                if mn == "update" or mn == "onUpdate" or mn == "lateUpdate" or mn == "doUpdate" then
                    pcall(function()
                        sdk.hook(m,
                            function(args) 
                                if cam_blocked then return sdk.PreHookResult.SKIP_ORIGINAL end
                                return sdk.PreHookResult.CALL_ORIGINAL 
                            end,
                            function(retval) return retval end)
                        cam_system_hooked = true
                    end)
                end
            end
        end
    end
    
    pcall(function()
        local mp = imgui.get_mouse()
        if mp then mouse_ok = true; table.insert(log_msgs, string.format("Mouse API OK: [%.0f, %.0f]", mp.x, mp.y)) end
    end)
    if not mouse_ok then table.insert(log_msgs, "Mouse API: not available") end
    status_msg = cam_system_hooked and "Hooks OK" or "No hooks"
end

local function activate_freecam()
    if not cam_system_hooked then install_hooks() end
    local pos = get_real_camera_pos()
    if not pos then status_msg = "No pos"; return false end
    freecam_pos = pos
    
    -- Capture the ENTIRE current matrix (rotation + position)
    captured_matrix = capture_current_matrix()
    
    freecam_yaw = 0; freecam_pitch = 0
    cam_blocked = true
    prev_mouse_x = nil; prev_mouse_y = nil; user_has_rotated = false; yaw_pitch_initialized = false
    lockscene_write_count = 0; joint_buf_write_count = 0
    
    if freeze_player then
        local updater = get_player_updater()
        if updater then pcall(function() updater:set_Enabled(false) end) end
    end
    
    status_msg = string.format("FREECAM [%.1f, %.1f, %.1f] mat:%s",
        pos.x, pos.y, pos.z, captured_matrix and "OK" or "NONE")
    return true
end

local function unlock_camera()
    if use_custom_fov and original_fov then
        local cam = get_primary_camera()
        if cam then pcall(function() cam:call("set_FOV", original_fov) end) end
    end
    use_custom_fov = false
    cam_blocked = false; freecam_pos = nil; freecam_mode = false
    captured_matrix = nil; prev_mouse_x = nil; prev_mouse_y = nil
    user_has_rotated = false
    
    if freeze_player then
        local updater = get_player_updater()
        if updater then pcall(function() updater:set_Enabled(true) end) end
    end
    
    status_msg = "Released."
end

local function is_key_down(vk) return reframework:is_key_down(vk) end

-- Main input loop
re.on_pre_application_entry("LateUpdateBehavior", function()

    if freecam_mode and freecam_pos then
        -- Mouse look (Hold mapped Look Key)
        local look_vk = look_key_vks[look_key_index]
        if is_key_down(look_vk) then
            pcall(function()
                local mp = imgui.get_mouse()
                if mp then
                    mouse_ok = true
                    local mx, my = mp.x, mp.y
                    if prev_mouse_x and prev_mouse_y then
                        local dx = mx - prev_mouse_x
                        local dy = my - prev_mouse_y
                        if math.abs(dx) > 0.5 or math.abs(dy) > 0.5 then
                            -- Initialize yaw/pitch from captured matrix on first rotation
                            if not yaw_pitch_initialized and captured_matrix then
                                -- m[10] = -sp, m[9] = sy*cp, m[11] = cy*cp
                                freecam_pitch = math.asin(math.max(-1, math.min(1, -captured_matrix[10])))
                                freecam_yaw = math.atan(captured_matrix[9], captured_matrix[11])
                                yaw_pitch_initialized = true
                            end
                            freecam_yaw = freecam_yaw - dx * mouse_sensitivity
                            freecam_pitch = freecam_pitch - dy * mouse_sensitivity
                            user_has_rotated = true
                        end
                    end
                    prev_mouse_x = mx; prev_mouse_y = my
                end
            end)
            if freecam_pitch > 1.5 then freecam_pitch = 1.5 end
            if freecam_pitch < -1.5 then freecam_pitch = -1.5 end
        else
            prev_mouse_x = nil; prev_mouse_y = nil
        end
        
        -- Q/E rotation
        if is_key_down(VK_Q) or is_key_down(VK_E) then
            if not yaw_pitch_initialized and captured_matrix then
                freecam_pitch = math.asin(math.max(-1, math.min(1, -captured_matrix[10])))
                freecam_yaw = math.atan(captured_matrix[9], captured_matrix[11])
                yaw_pitch_initialized = true
            end
            if is_key_down(VK_Q) then freecam_yaw = freecam_yaw + 0.02 end
            if is_key_down(VK_E) then freecam_yaw = freecam_yaw - 0.02 end
            user_has_rotated = true
        end
        
        -- WASD direction: use captured matrix rotation when no user rotation,
        -- or yaw/pitch when user has rotated
        local speed = move_speed
        if is_key_down(VK_SHIFT) then speed = speed * fast_multiplier end
        
        local fwd_x, fwd_y, fwd_z = 0, 0, -1
        local right_x, right_y, right_z = 1, 0, 0
        
        if user_has_rotated then
            local cy = math.cos(freecam_yaw); local sy = math.sin(freecam_yaw)
            local cp = math.cos(freecam_pitch); local sp = math.sin(freecam_pitch)
            fwd_x = -(sy * cp); fwd_y = sp; fwd_z = -(cy * cp)
            right_x = cy; right_y = 0; right_z = -sy
        elseif captured_matrix then
            -- Extract direction from captured matrix
            -- Row 2 = forward (negate for camera -Z convention)
            fwd_x = -captured_matrix[9]; fwd_y = -captured_matrix[10]; fwd_z = -captured_matrix[11]
            -- Row 0 = right
            right_x = captured_matrix[1]; right_y = captured_matrix[2]; right_z = captured_matrix[3]
        end
        
        if is_key_down(VK_W) then freecam_pos.x=freecam_pos.x+fwd_x*speed; freecam_pos.y=freecam_pos.y+fwd_y*speed; freecam_pos.z=freecam_pos.z+fwd_z*speed end
        if is_key_down(VK_S) then freecam_pos.x=freecam_pos.x-fwd_x*speed; freecam_pos.y=freecam_pos.y-fwd_y*speed; freecam_pos.z=freecam_pos.z-fwd_z*speed end
        if is_key_down(VK_A) then freecam_pos.x=freecam_pos.x-right_x*speed; freecam_pos.y=freecam_pos.y-right_y*speed; freecam_pos.z=freecam_pos.z-right_z*speed end
        if is_key_down(VK_D) then freecam_pos.x=freecam_pos.x+right_x*speed; freecam_pos.y=freecam_pos.y+right_y*speed; freecam_pos.z=freecam_pos.z+right_z*speed end
        if is_key_down(VK_SPACE) then freecam_pos.y=freecam_pos.y+speed end
        if is_key_down(VK_CTRL) then freecam_pos.y=freecam_pos.y-speed end
    end
end)

-- Write at LockScene
re.on_pre_application_entry("LockScene", function()
    if freecam_mode and freecam_pos then
        if user_has_rotated then
            write_yawpitch_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z, freecam_yaw, freecam_pitch)
        else
            write_frozen_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z)
        end
        lockscene_write_count = lockscene_write_count + 1

        -- Apply Custom Global FOV if enabled
        if use_custom_fov or disable_dof then
            pcall(function()
                local cam = get_primary_camera()
                if cam then 
                    if use_custom_fov then cam:call("set_FOV", global_fov) end
                    if disable_dof then
                        local go = cam:call("get_GameObject")
                        if go then
                            local dof = go:call("getComponent(System.Type)", sdk.typeof("via.render.DepthOfField"))
                            if dof then dof:call("set_Enabled", false) end
                        end
                    end
                end
            end)
        end
    end
end)

-- Write at BeginRendering
re.on_pre_application_entry("BeginRendering", function()
    -- FreeCam Toggle Hotkey
    if toggle_vk ~= 0 then
        local is_toggle_down = is_key_down(toggle_vk)
        if is_toggle_down and not prev_toggle_down then
            if freecam_mode then
                unlock_camera()
            else
                if not cam_system_hooked then install_hooks() end
                if activate_freecam() then freecam_mode = true end
            end
        end
        prev_toggle_down = is_toggle_down
    end

    -- Character Freeze Hotkey
    if freeze_hotkey_vk ~= 0 then
        local is_freeze_down = is_key_down(freeze_hotkey_vk)
        if is_freeze_down and not prev_freeze_hotkey_down then
            freeze_player = not freeze_player
            save_config()
            if freecam_mode then
                local updater = get_player_updater()
                if updater then 
                    pcall(function() updater:set_Enabled(not freeze_player) end) 
                    status_msg = freeze_player and "Player Frozen" or "Player Unfrozen"
                end
            end
        end
        prev_freeze_hotkey_down = is_freeze_down
    end

    if freecam_mode and freecam_pos then
        if user_has_rotated then
            write_yawpitch_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z, freecam_yaw, freecam_pitch)
        else
            write_frozen_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z)
        end
    end
end)

re.on_draw_ui(function()
    if not reframework:is_drawing_ui() then return end

    if imgui.tree_node("RE9 FREECAM CED v1.0.3") then

        imgui.separator()
        
        if not freecam_mode then
            if imgui.button("  ACTIVATE FREECAM  ") then 
                if not cam_system_hooked then install_hooks() end
                if activate_freecam() then freecam_mode = true end 
            end
            imgui.same_line()
            imgui.text_colored("RE9 FREECAM Disabled", 0xFFAAAAAA)
        else
            if imgui.button("  DEACTIVATE FREECAM  ") then unlock_camera() end
            imgui.same_line()
            imgui.text_colored("RE9 FREECAM Enabled", 0xFF00FF00)
        end
        
        imgui.spacing()
        
        -- FreeCam Hotkey
        if waiting_for_toggle_key then
            imgui.button(" Press any key... ")
            for i = 3, 255 do
                if reframework:is_key_down(i) then
                    toggle_vk = i
                    waiting_for_toggle_key = false
                    save_config()
                    break
                end
            end
        else
            local btn_label = toggle_vk == 0 and " Not bound " or (" " .. get_vk_name(toggle_vk) .. " ")
            if imgui.button(btn_label) then
                waiting_for_toggle_key = true
            end
        end
        imgui.same_line()
        imgui.text("Toggle FreeCam Hotkey")
        
        -- Character Freeze Hotkey
        if waiting_for_freeze_key then
            imgui.button(" Press any key...  ")
            for i = 3, 255 do
                if reframework:is_key_down(i) then
                    freeze_hotkey_vk = i
                    waiting_for_freeze_key = false
                    save_config()
                    break
                end
            end
        else
            local btn_label = freeze_hotkey_vk == 0 and " Not bound  " or (" " .. get_vk_name(freeze_hotkey_vk) .. "  ")
            if imgui.button(btn_label .. "##freeze") then
                waiting_for_freeze_key = true
            end
        end
        imgui.same_line()
        imgui.text("Toggle Freeze Hotkey")

        imgui.spacing()

        if freecam_mode then
            if freecam_pos then
                imgui.text(string.format("Pos: [%.2f, %.2f, %.2f]", freecam_pos.x, freecam_pos.y, freecam_pos.z))
            end
            if user_has_rotated then
                imgui.text(string.format("Yaw: %.1f° Pitch: %.1f°", math.deg(freecam_yaw), math.deg(freecam_pitch)))
            end
            imgui.text("WASD=Move | Q/E=Rotate | Space/Ctrl=Up/Dn")
            imgui.text("Mouse=Look | Shift=Fast")
            
            local changed = false
            changed, move_speed = imgui.slider_float("Speed", move_speed, 0.005, 5.0)
            if changed then save_config() end

            changed, mouse_sensitivity = imgui.slider_float("Mouse Sens", mouse_sensitivity, 0.001, 0.02)
            if changed then save_config() end
            
            changed, look_key_index = imgui.combo("Look Key", look_key_index, look_key_names)
            if changed then save_config() end

            imgui.spacing()
            local prev_use_fov = use_custom_fov
            changed, use_custom_fov = imgui.checkbox("Use Custom Global FOV", use_custom_fov)
            if changed then
                if use_custom_fov and not prev_use_fov then
                    local cam = get_primary_camera()
                    if cam then pcall(function() original_fov = cam:call("get_FOV") end) end
                elseif not use_custom_fov and prev_use_fov and original_fov then
                    local cam = get_primary_camera()
                    if cam then pcall(function() cam:call("set_FOV", original_fov) end) end
                end
                save_config()
            end

            if use_custom_fov then
                changed, global_fov = imgui.slider_float("Global FOV", global_fov, 10.0, 160.0)
                if changed then save_config() end
            end

            changed, disable_dof = imgui.checkbox("Disable Depth of Field", disable_dof)
            if changed then save_config() end
            
            local prev_freeze = freeze_player
            changed, freeze_player = imgui.checkbox("Freeze Player Movement on Activate", freeze_player)
            if changed then
                save_config()
                if freecam_mode then
                    local updater = get_player_updater()
                    if updater then pcall(function() updater:set_Enabled(not freeze_player) end) end
                end
            end
        end

        -- Developer Signature
        imgui.spacing()
        imgui.text_colored("CED v1.0.3", 0xFFAAAAAA)
        
        imgui.tree_pop()
    end
end)

-- BEGIN RE9_AESTHETIC_POSE_LOGGER
local re9_pose_logger = re9_pose_logger or {}
-- REFramework Lua may reject absolute paths. json/io paths are relative to reframework/data here.
re9_pose_logger.data_dir = re9_pose_logger.data_dir or ""
re9_pose_logger.control_file = re9_pose_logger.control_file or "re9_pose_control.json"
re9_pose_logger.status_file = re9_pose_logger.status_file or "re9_pose_status.json"
re9_pose_logger.pose_log_file = re9_pose_logger.pose_log_file or "re9_freecam_pose_log.csv"
re9_pose_logger.interval_sec = re9_pose_logger.interval_sec or 0.033333
re9_pose_logger.enabled = re9_pose_logger.enabled ~= false
re9_pose_logger.logging = re9_pose_logger.logging or false
re9_pose_logger.session_id = re9_pose_logger.session_id or ""
re9_pose_logger.rows_written = re9_pose_logger.rows_written or 0
re9_pose_logger.last_error = re9_pose_logger.last_error or ""
re9_pose_logger.last_sample_clock = re9_pose_logger.last_sample_clock or 0
re9_pose_logger.last_control_clock = re9_pose_logger.last_control_clock or 0
re9_pose_logger.session_start_clock = re9_pose_logger.session_start_clock or 0
re9_pose_logger.file_handle = re9_pose_logger.file_handle or nil
re9_pose_logger.last_command_id = re9_pose_logger.last_command_id or ""
re9_pose_logger.scan_pose_enabled = re9_pose_logger.scan_pose_enabled or false
re9_pose_logger.scan_segment_id = re9_pose_logger.scan_segment_id or ""
re9_pose_logger.scan_x = re9_pose_logger.scan_x or 0
re9_pose_logger.scan_y = re9_pose_logger.scan_y or 0
re9_pose_logger.scan_z = re9_pose_logger.scan_z or 0
re9_pose_logger.scan_x_start = re9_pose_logger.scan_x_start or 0
re9_pose_logger.scan_y_start = re9_pose_logger.scan_y_start or 0
re9_pose_logger.scan_z_start = re9_pose_logger.scan_z_start or 0
re9_pose_logger.scan_x_end = re9_pose_logger.scan_x_end or 0
re9_pose_logger.scan_y_end = re9_pose_logger.scan_y_end or 0
re9_pose_logger.scan_z_end = re9_pose_logger.scan_z_end or 0
re9_pose_logger.scan_yaw = re9_pose_logger.scan_yaw or 0
re9_pose_logger.scan_yaw_start = re9_pose_logger.scan_yaw_start or 0
re9_pose_logger.scan_yaw_end = re9_pose_logger.scan_yaw_end or 0
re9_pose_logger.scan_pitch = re9_pose_logger.scan_pitch or 0
re9_pose_logger.scan_pitch_start = re9_pose_logger.scan_pitch_start or 0
re9_pose_logger.scan_pitch_end = re9_pose_logger.scan_pitch_end or 0
re9_pose_logger.scan_fov = re9_pose_logger.scan_fov or nil
re9_pose_logger.scan_fov_start = re9_pose_logger.scan_fov_start or nil
re9_pose_logger.scan_fov_end = re9_pose_logger.scan_fov_end or nil
re9_pose_logger.scan_start_clock = re9_pose_logger.scan_start_clock or 0
re9_pose_logger.scan_duration_sec = re9_pose_logger.scan_duration_sec or 0
re9_pose_logger.trajectory_enabled = re9_pose_logger.trajectory_enabled or false
re9_pose_logger.trajectory_id = re9_pose_logger.trajectory_id or ""
re9_pose_logger.trajectory_keyframes = re9_pose_logger.trajectory_keyframes or nil
re9_pose_logger.trajectory_start_clock = re9_pose_logger.trajectory_start_clock or 0
re9_pose_logger.trajectory_duration_sec = re9_pose_logger.trajectory_duration_sec or 0
re9_pose_logger.trajectory_frame_count = re9_pose_logger.trajectory_frame_count or 0
re9_pose_logger.physics_probe_status = re9_pose_logger.physics_probe_status or "not run"
re9_pose_logger.physics_probe_contacts = re9_pose_logger.physics_probe_contacts or 0
re9_pose_logger.physics_probe_rays = re9_pose_logger.physics_probe_rays or 0
re9_pose_logger.physics_probe_pose_valid = re9_pose_logger.physics_probe_pose_valid ~= false
re9_pose_logger.physics_probe_details = re9_pose_logger.physics_probe_details or ""
re9_pose_logger.physics_probe_error = re9_pose_logger.physics_probe_error or ""
re9_pose_logger.physics_clip_distance = re9_pose_logger.physics_clip_distance or 0.03
re9_pose_logger.physics_near_distance = re9_pose_logger.physics_near_distance or 0.12
re9_pose_logger.physics_sphere_radius = re9_pose_logger.physics_sphere_radius or 0.08
re9_pose_logger.physics_saturation_invalid = re9_pose_logger.physics_saturation_invalid ~= false
re9_pose_logger.physics_filter_layer = re9_pose_logger.physics_filter_layer or 0
re9_pose_logger.physics_filter_mask_bit = re9_pose_logger.physics_filter_mask_bit or 31
re9_pose_logger.new_scene_points_file = re9_pose_logger.new_scene_points_file or "re9_new_scene_points.csv"
re9_pose_logger.new_scene_points_json_file = re9_pose_logger.new_scene_points_json_file or "re9_new_scene_points.json"
re9_pose_logger.new_scene_point_count = re9_pose_logger.new_scene_point_count or 0
re9_pose_logger.new_scene_last_point = re9_pose_logger.new_scene_last_point or ""
local re9_pose_is_freecam_mode
local re9_pose_get_pose

local function re9_pose_escape_json(value)
    value = tostring(value or "")
    value = value:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n')
    return value
end

local function re9_pose_basename(path)
    path = tostring(path or "")
    path = path:gsub('\\', '/')
    local name = path:match('([^/]+)$') or path
    if name == "" then name = "re9_freecam_pose_log.csv" end
    return name
end

local function re9_pose_data_path(name)
    name = re9_pose_basename(name)
    if re9_pose_logger.data_dir == nil or re9_pose_logger.data_dir == "" then return name end
    return re9_pose_logger.data_dir .. "/" .. name
end

local function re9_pose_csv_path(path)
    return re9_pose_data_path(re9_pose_basename(path or re9_pose_logger.pose_log_file))
end

local function re9_pose_write_status()
    local payload = {
        session_id = re9_pose_logger.session_id or "",
        logging = re9_pose_logger.logging == true,
        rows_written = re9_pose_logger.rows_written or 0,
        pose_log_file = re9_pose_logger.pose_log_file or "",
        scan_pose_enabled = re9_pose_logger.scan_pose_enabled == true,
        scan_segment_id = re9_pose_logger.scan_segment_id or "",
        trajectory_enabled = re9_pose_logger.trajectory_enabled == true,
        trajectory_id = re9_pose_logger.trajectory_id or "",
        trajectory_frame_count = re9_pose_logger.trajectory_frame_count or 0,
        physics_probe_status = re9_pose_logger.physics_probe_status or "",
        physics_probe_contacts = re9_pose_logger.physics_probe_contacts or 0,
        physics_probe_rays = re9_pose_logger.physics_probe_rays or 0,
        physics_probe_pose_valid = re9_pose_logger.physics_probe_pose_valid == true,
        physics_probe_details = re9_pose_logger.physics_probe_details or "",
        physics_probe_error = re9_pose_logger.physics_probe_error or "",
        new_scene_point_count = re9_pose_logger.new_scene_point_count or 0,
        new_scene_last_point = re9_pose_logger.new_scene_last_point or "",
        new_scene_points_file = re9_pose_logger.new_scene_points_file or "",
        last_error = re9_pose_logger.last_error or ""
    }
    local ok, err = pcall(function()
        if json ~= nil and json.dump_file ~= nil then
            json.dump_file(re9_pose_logger.status_file, payload)
        else
            local f = assert(io.open(re9_pose_data_path(re9_pose_logger.status_file), "w"))
            f:write(string.format('{"session_id":"%s","logging":%s,"rows_written":%d,"pose_log_file":"%s","scan_pose_enabled":%s,"scan_segment_id":"%s","trajectory_enabled":%s,"trajectory_id":"%s","trajectory_frame_count":%d,"physics_probe_status":"%s","physics_probe_contacts":%d,"physics_probe_rays":%d,"physics_probe_pose_valid":%s,"physics_probe_details":"%s","physics_probe_error":"%s","new_scene_point_count":%d,"new_scene_last_point":"%s","new_scene_points_file":"%s","last_error":"%s"}',
                re9_pose_escape_json(payload.session_id), tostring(payload.logging), tonumber(payload.rows_written) or 0,
                re9_pose_escape_json(payload.pose_log_file), tostring(payload.scan_pose_enabled), re9_pose_escape_json(payload.scan_segment_id),
                tostring(payload.trajectory_enabled), re9_pose_escape_json(payload.trajectory_id), tonumber(payload.trajectory_frame_count) or 0,
                re9_pose_escape_json(payload.physics_probe_status), tonumber(payload.physics_probe_contacts) or 0, tonumber(payload.physics_probe_rays) or 0,
                tostring(payload.physics_probe_pose_valid), re9_pose_escape_json(payload.physics_probe_details),
                re9_pose_escape_json(payload.physics_probe_error), tonumber(payload.new_scene_point_count) or 0,
                re9_pose_escape_json(payload.new_scene_last_point), re9_pose_escape_json(payload.new_scene_points_file),
                re9_pose_escape_json(payload.last_error)))
            f:close()
        end
    end)
    if not ok then re9_pose_logger.last_error = tostring(err) end
end

local function re9_pose_read_control()
    local ok, data = pcall(function()
        if json ~= nil and json.load_file ~= nil then return json.load_file(re9_pose_logger.control_file) end
        local f = io.open(re9_pose_data_path(re9_pose_logger.control_file), "r")
        if f == nil then return nil end
        local text = f:read("*a")
        f:close()
        if text == nil then return nil end
        return {
            command = text:match('"command"%s*:%s*"([^"]+)"'),
            command_id = text:match('"command_id"%s*:%s*"([^"]+)"'),
            session_id = text:match('"session_id"%s*:%s*"([^"]+)"'),
            pose_log_file = text:match('"pose_log_file"%s*:%s*"([^"]+)"'),
            interval_sec = tonumber(text:match('"interval_sec"%s*:%s*([%-%d%.]+)')),
            x = tonumber(text:match('"x"%s*:%s*([%-%d%.]+)')),
            y = tonumber(text:match('"y"%s*:%s*([%-%d%.]+)')),
            z = tonumber(text:match('"z"%s*:%s*([%-%d%.]+)')),
            x_end = tonumber(text:match('"x_end"%s*:%s*([%-%d%.]+)')),
            y_end = tonumber(text:match('"y_end"%s*:%s*([%-%d%.]+)')),
            z_end = tonumber(text:match('"z_end"%s*:%s*([%-%d%.]+)')),
            yaw = tonumber(text:match('"yaw"%s*:%s*([%-%d%.]+)')),
            yaw_end = tonumber(text:match('"yaw_end"%s*:%s*([%-%d%.]+)')),
            duration_sec = tonumber(text:match('"duration_sec"%s*:%s*([%-%d%.]+)')),
            pitch = tonumber(text:match('"pitch"%s*:%s*([%-%d%.]+)')),
            pitch_end = tonumber(text:match('"pitch_end"%s*:%s*([%-%d%.]+)')),
            fov = tonumber(text:match('"fov"%s*:%s*([%-%d%.]+)')),
            fov_end = tonumber(text:match('"fov_end"%s*:%s*([%-%d%.]+)')),
            segment_id = text:match('"segment_id"%s*:%s*"([^"]+)"')
        }
    end)
    if ok then return data end
    re9_pose_logger.last_error = tostring(data)
    return nil
end

local function re9_pose_vec3(x, y, z)
    if Vector3f ~= nil and Vector3f.new ~= nil then return Vector3f.new(x, y, z) end
    return { x = x, y = y, z = z }
end

local function re9_pose_call_query(query, method_name, ...)
    if query == nil or query.call == nil then return false, "query has no call method" end
    local ok, result = pcall(function(...) return query:call(method_name, ...) end, ...)
    if ok then return true, result end
    return false, tostring(result)
end

local function re9_pose_contact_min_distance(result, count)
    local min_distance = nil
    local max_index = (tonumber(count) or 0) - 1
    if max_index > 7 then max_index = 7 end
    for i = 0, max_index do
        local ok_cp, cp = pcall(function() return result:call("getContactPoint", i) end)
        if ok_cp and cp ~= nil then
            local d = nil
            if type(cp) == "table" then d = tonumber(cp.Distance or cp.distance) end
            if d == nil then pcall(function() d = tonumber(cp:get_field("Distance")) end) end
            if d == nil then pcall(function() d = tonumber(cp:call("get_Distance")) end) end
            if d ~= nil and (min_distance == nil or d < min_distance) then min_distance = d end
        end
    end
    return min_distance
end

local function re9_pose_run_single_cast_ray(origin, target, inside_hits, filter)
    if sdk == nil then return false, "sdk unavailable", 0 end
    local physics_type = sdk.find_type_definition("via.physics.System")
    if physics_type == nil then return false, "via.physics.System type not found", 0 end
    local query = sdk.create_instance("via.physics.CastRayQuery")
    if query == nil then query = sdk.create_instance("via.physics.CastRayQuery", true) end
    if query == nil then return false, "could not create CastRayQuery", 0 end
    re9_pose_call_query(query, "clearOptions")
    re9_pose_call_query(query, "enableAllHits")
    re9_pose_call_query(query, "enableOneHitBreak")
    if inside_hits then re9_pose_call_query(query, "enableInsideHits") end
    if filter ~= nil then
        re9_pose_call_query(query, "copyFilterInfo(via.physics.FilterInfo)", filter)
        re9_pose_call_query(query, "copyFilterInfo", filter)
        re9_pose_call_query(query, "set_FilterInfo(via.physics.FilterInfo)", filter)
        re9_pose_call_query(query, "set_FilterInfo", filter)
    end
    local ok_set, set_err = re9_pose_call_query(query, "setRay(via.vec3, via.vec3)", origin, target)
    if not ok_set then ok_set, set_err = re9_pose_call_query(query, "setRay", origin, target) end
    if not ok_set then return false, "setRay failed: " .. tostring(set_err), 0 end
    local ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, "castRay(via.physics.CastRayQuery)", query) end)
    if not ok_cast then ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, "castRay", query) end) end
    if not ok_cast or result == nil then return false, "castRay failed: " .. tostring(result), 0 end
    local ok_num, num = pcall(function() return result:call("get_NumContactPoints") end)
    if not ok_num then ok_num, num = pcall(function() return result:call("get_NumContactPoints()") end) end
    if not ok_num then return false, "get_NumContactPoints failed: " .. tostring(num), 0 end
    num = tonumber(num) or 0
    return true, "api_ok", num, re9_pose_contact_min_distance(result, num)
end

local function re9_pose_create_filter_info(layer, mask_bits)
    if sdk == nil then return nil end
    local filter = sdk.create_instance("via.physics.FilterInfo")
    if filter == nil then filter = sdk.create_instance("via.physics.FilterInfo", true) end
    if filter ~= nil then
        pcall(function() filter:call(".ctor") end)
        local filter_layer = tonumber(layer) or 0
        local filter_mask = tonumber(mask_bits) or 0xffffffff
        pcall(function() filter:call("set_Layer", filter_layer) end)
        pcall(function() filter:call("set_Layer(System.UInt32)", filter_layer) end)
        pcall(function() filter:call("set_MaskBits", filter_mask) end)
        pcall(function() filter:call("set_MaskBits(System.UInt32)", filter_mask) end)
    end
    return filter
end

local function re9_pose_current_filter()
    local layer = math.floor(tonumber(re9_pose_logger.physics_filter_layer) or 0)
    if layer < 0 then layer = 0 elseif layer > 31 then layer = 31 end
    local mask_bit = math.floor(tonumber(re9_pose_logger.physics_filter_mask_bit) or 31)
    if mask_bit < 0 then mask_bit = 0 elseif mask_bit > 31 then mask_bit = 31 end
    local mask_bits = 2 ^ mask_bit
    return re9_pose_create_filter_info(layer, mask_bits), layer, mask_bit, mask_bits
end

local function re9_pose_run_closest_sphere(center, radius, filter, mask_bits)
    if sdk == nil then return false, "sdk unavailable", 0 end
    local physics_type = sdk.find_type_definition("via.physics.System")
    if physics_type == nil then return false, "via.physics.System type not found", 0 end
    local sphere = sdk.create_instance("via.Sphere")
    if sphere == nil then sphere = sdk.create_instance("via.Sphere", true) end
    if sphere == nil then return false, "could not create via.Sphere", 0 end
    pcall(function() sphere:call(".ctor", center, radius) end)
    pcall(function() sphere:call("setPos", center) end)
    pcall(function() sphere:call("setRadius", radius) end)
    pcall(function() sphere:call("set_Center", center) end)
    pcall(function() sphere:call("set_Radius", radius) end)
    pcall(function() sphere:set_field("pos", center) end)
    pcall(function() sphere:set_field("r", radius) end)
    if filter == nil then filter = re9_pose_create_filter_info() end
    if filter == nil then return false, "could not create FilterInfo", 0 end
    local mask = tonumber(mask_bits) or 0xffffffff
    local ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, "closestSphere(via.Sphere, System.UInt32, via.physics.FilterInfo)", sphere, mask, filter) end)
    if not ok_cast then ok_cast, result = pcall(function() return sdk.call_native_func(nil, physics_type, "closestSphere", sphere, mask, filter) end) end
    if not ok_cast or result == nil then return false, "closestSphere failed: " .. tostring(result), 0 end
    local ok_num, num = pcall(function() return result:call("get_NumContactPoints") end)
    if not ok_num then ok_num, num = pcall(function() return result:call("get_NumContactPoints()") end) end
    if not ok_num then return false, "closestSphere get_NumContactPoints failed: " .. tostring(num), 0 end
    return true, "api_ok", tonumber(num) or 0
end

local function re9_pose_run_resolve_penetration(center, radius, filter)
    if sdk == nil then return false, "sdk unavailable", false end
    local physics_type = sdk.find_type_definition("via.physics.System")
    if physics_type == nil then return false, "via.physics.System type not found", false end
    local sphere = sdk.create_instance("via.Sphere")
    if sphere == nil then sphere = sdk.create_instance("via.Sphere", true) end
    if sphere == nil then return false, "could not create via.Sphere", false end
    pcall(function() sphere:call(".ctor", center, radius) end)
    pcall(function() sphere:call("setPos", center) end)
    pcall(function() sphere:call("setRadius", radius) end)
    pcall(function() sphere:call("set_Center", center) end)
    pcall(function() sphere:call("set_Radius", radius) end)
    pcall(function() sphere:set_field("pos", center) end)
    pcall(function() sphere:set_field("r", radius) end)
    if filter == nil then filter = re9_pose_create_filter_info() end
    if filter == nil then return false, "could not create FilterInfo", false end
    local ok_hit, result = pcall(function() return sdk.call_native_func(nil, physics_type, "resolvePenetration(via.Sphere, via.physics.FilterInfo)", sphere, filter) end)
    if not ok_hit then ok_hit, result = pcall(function() return sdk.call_native_func(nil, physics_type, "resolvePenetration", sphere, filter) end) end
    if not ok_hit then return false, "resolvePenetration failed: " .. tostring(result), false end
    return true, "api_ok", result == true
end

local function re9_pose_probe_dirs()
    local dirs = {}
    for dx = -1, 1 do
        for dy = -1, 1 do
            for dz = -1, 1 do
                if not (dx == 0 and dy == 0 and dz == 0) then
                    local len = math.sqrt(dx * dx + dy * dy + dz * dz)
                    table.insert(dirs, { string.format("%+d%+d%+d", dx, dy, dz), dx / len, dy / len, dz / len })
                end
            end
        end
    end
    return dirs
end

local function re9_pose_forward_dir(yaw_value, pitch_value)
    local yaw = tonumber(yaw_value) or 0
    local pitch = tonumber(pitch_value) or 0
    local cp = math.cos(pitch)
    return math.sin(yaw) * cp, -math.sin(pitch), math.cos(yaw) * cp
end

local function re9_pose_call_obj(obj, method_name, ...)
    if obj == nil or obj.call == nil then return false, "object has no call method" end
    local ok, result = pcall(function(...) return obj:call(method_name, ...) end, ...)
    if ok then return true, result end
    return false, tostring(result)
end

local function re9_pose_obj_field(obj, field_name)
    if obj == nil then return nil end
    local ok, value = pcall(function() return obj:get_field(field_name) end)
    if ok then return value end
    return nil
end

local function re9_pose_get_singleton(type_name)
    if sdk == nil or sdk.get_managed_singleton == nil then return nil, "sdk.get_managed_singleton unavailable" end
    local ok, obj = pcall(function() return sdk.get_managed_singleton(type_name) end)
    if ok and obj ~= nil then return obj, "singleton" end
    return nil, tostring(obj)
end

local function re9_pose_array_elements(value)
    if value == nil then return {} end
    local ok, elements = pcall(function() return value:get_elements() end)
    if ok and elements ~= nil then return elements end
    return {}
end

local function re9_pose_scene_by_method(method_name)
    if sdk == nil then return nil, "sdk unavailable" end
    local scene_manager_type = sdk.find_type_definition("via.SceneManager")
    if scene_manager_type == nil then return nil, "via.SceneManager type missing" end
    local method = scene_manager_type:get_method(method_name)
    if method == nil then return nil, method_name .. " method missing" end
    local ok, scene = pcall(function() return method:call(nil) end)
    if ok and scene ~= nil then return scene, method_name end
    return nil, tostring(scene)
end

local function re9_pose_find_scene_components(type_name, parts)
    local component_type = nil
    local ok_type, type_result = pcall(function() return sdk.typeof(type_name) end)
    if ok_type then component_type = type_result end
    if component_type == nil then
        table.insert(parts, type_name .. " typeof=nil")
        return {}
    end
    local out = {}
    local seen = {}
    local scene_methods = {"get_CurrentScene", "get_MainScene", "get_ResidentScene"}
    for _, method_name in ipairs(scene_methods) do
        local scene, scene_src = re9_pose_scene_by_method(method_name)
        if scene ~= nil then
            local ok_find, components = pcall(function() return scene:call("findComponents(System.Type)", component_type) end)
            if not ok_find then ok_find, components = pcall(function() return scene:call("findComponents", component_type) end) end
            local elements = re9_pose_array_elements(components)
            local count = 0
            for _, component in ipairs(elements) do
                if component ~= nil and seen[component] ~= true then
                    seen[component] = true
                    table.insert(out, component)
                    count = count + 1
                end
            end
            table.insert(parts, type_name .. "@" .. tostring(scene_src) .. "=" .. tostring(count))
        else
            table.insert(parts, type_name .. "@" .. tostring(method_name) .. "=scene_nil:" .. tostring(scene_src))
        end
    end
    return out
end

local function re9_pose_vec3_text(value)
    if value == nil then return "nil" end
    local x = nil
    local y = nil
    local z = nil
    pcall(function() x = value.x or value[1] end)
    pcall(function() y = value.y or value[2] end)
    pcall(function() z = value.z or value[3] end)
    return string.format("(%.2f,%.2f,%.2f)", tonumber(x) or 0, tonumber(y) or 0, tonumber(z) or 0)
end

local function re9_pose_probe_camera_interp(label, obj, parts)
    if obj == nil then return 0 end
    local score = 0
    local ok_rate, rate = re9_pose_call_obj(obj, "get_CollisionStateRate")
    if not ok_rate then ok_rate, rate = re9_pose_call_obj(obj, "get_CollisionStateRate()") end
    local ok_pos, pos = re9_pose_call_obj(obj, "get_CameraPosition")
    if not ok_pos then ok_pos, pos = re9_pose_call_obj(obj, "get_CameraPosition()") end
    if ok_rate and tonumber(rate) ~= nil and math.abs(tonumber(rate)) > 0.001 then score = score + 1 end
    table.insert(parts, label .. ":rate=" .. tostring(ok_rate and rate or "?") .. ":pos=" .. tostring(ok_pos and re9_pose_vec3_text(pos) or "?"))
    local collision = re9_pose_obj_field(obj, "_CollisionInterpolation")
    if collision ~= nil then
        local ok_radius, radius = re9_pose_call_obj(collision, "getCollisionRadius")
        local ok_range, range = re9_pose_call_obj(collision, "getCollisionRange")
        local ok_avoid, avoid = re9_pose_call_obj(collision, "get_AvoidRate")
        local ok_cpos, cpos = re9_pose_call_obj(collision, "get_CameraPosition")
        if ok_avoid and tonumber(avoid) ~= nil and math.abs(tonumber(avoid)) > 0.001 then score = score + 1 end
        table.insert(parts, label .. ":collision=live:r=" .. tostring(ok_radius and radius or "?") .. ":range=" .. tostring(ok_range and range or "?") .. ":avoid=" .. tostring(ok_avoid and avoid or "?") .. ":cpos=" .. tostring(ok_cpos and re9_pose_vec3_text(cpos) or "?"))
    else
        table.insert(parts, label .. ":collision=nil")
    end
    return score
end

local function re9_pose_probe_camera_collision_system()
    local parts = {}
    local score = 0
    local found = 0
    local fps, fps_src = re9_pose_get_singleton("app.PlayerFPSCameraController")
    local tps, tps_src = re9_pose_get_singleton("app.PlayerTPSCameraController")
    if fps ~= nil then
        found = found + 1
        table.insert(parts, "FPSController=" .. tostring(fps_src))
        local ok_interp, interp = re9_pose_call_obj(fps, "get_FPSActionInterpolation")
        if ok_interp and interp ~= nil then score = score + re9_pose_probe_camera_interp("FPSInterp", interp, parts) else table.insert(parts, "FPSInterp=nil") end
        local ok_pos, pos = re9_pose_call_obj(fps, "get_CameraPositionWithMovementShake")
        table.insert(parts, "FPSControllerPos=" .. tostring(ok_pos and re9_pose_vec3_text(pos) or "?"))
    else
        table.insert(parts, "FPSController=nil:" .. tostring(fps_src))
    end
    if tps ~= nil then
        found = found + 1
        table.insert(parts, "TPSController=" .. tostring(tps_src))
        local ok_interp, interp = re9_pose_call_obj(tps, "get_TPSActionInterpolation")
        if ok_interp and interp ~= nil then score = score + re9_pose_probe_camera_interp("TPSInterp", interp, parts) else table.insert(parts, "TPSInterp=nil") end
    else
        table.insert(parts, "TPSController=nil:" .. tostring(tps_src))
    end
    local fps_interp, fps_interp_src = re9_pose_get_singleton("app.PlayerCameraFPSActionInterpolation")
    if fps_interp ~= nil then found = found + 1; score = score + re9_pose_probe_camera_interp("FPSInterpSingleton", fps_interp, parts) else table.insert(parts, "FPSInterpSingleton=nil:" .. tostring(fps_interp_src)) end
    local tps_interp, tps_interp_src = re9_pose_get_singleton("app.PlayerCameraTPSActionInterpolation")
    if tps_interp ~= nil then found = found + 1; score = score + re9_pose_probe_camera_interp("TPSInterpSingleton", tps_interp, parts) else table.insert(parts, "TPSInterpSingleton=nil:" .. tostring(tps_interp_src)) end
    local scene_fps = re9_pose_find_scene_components("app.PlayerFPSCameraController", parts)
    for index, component in ipairs(scene_fps) do
        found = found + 1
        local ok_interp, interp = re9_pose_call_obj(component, "get_FPSActionInterpolation")
        if ok_interp and interp ~= nil then score = score + re9_pose_probe_camera_interp("SceneFPS" .. tostring(index), interp, parts) else table.insert(parts, "SceneFPS" .. tostring(index) .. ":interp=nil") end
        local ok_pos, pos = re9_pose_call_obj(component, "get_CameraPositionWithMovementShake")
        table.insert(parts, "SceneFPS" .. tostring(index) .. ":pos=" .. tostring(ok_pos and re9_pose_vec3_text(pos) or "?"))
    end
    local scene_tps = re9_pose_find_scene_components("app.PlayerTPSCameraController", parts)
    for index, component in ipairs(scene_tps) do
        found = found + 1
        local ok_interp, interp = re9_pose_call_obj(component, "get_TPSActionInterpolation")
        if ok_interp and interp ~= nil then score = score + re9_pose_probe_camera_interp("SceneTPS" .. tostring(index), interp, parts) else table.insert(parts, "SceneTPS" .. tostring(index) .. ":interp=nil") end
    end
    local scene_fps_interp = re9_pose_find_scene_components("app.PlayerCameraFPSActionInterpolation", parts)
    for index, component in ipairs(scene_fps_interp) do
        found = found + 1
        score = score + re9_pose_probe_camera_interp("SceneFPSInterp" .. tostring(index), component, parts)
    end
    local scene_tps_interp = re9_pose_find_scene_components("app.PlayerCameraTPSActionInterpolation", parts)
    for index, component in ipairs(scene_tps_interp) do
        found = found + 1
        score = score + re9_pose_probe_camera_interp("SceneTPSInterp" .. tostring(index), component, parts)
    end
    re9_pose_logger.physics_probe_status = score > 0 and "camera_collision_active" or "camera_collision_probe"
    re9_pose_logger.physics_probe_pose_valid = not (score > 0)
    re9_pose_logger.physics_probe_contacts = score
    re9_pose_logger.physics_probe_rays = found
    re9_pose_logger.physics_probe_details = table.concat(parts, "; ")
    re9_pose_logger.physics_probe_error = score > 0 and "Camera collision system reports active collision/avoidance." or "No live camera collision response found; scene component scan may not expose FreeCam collision objects."
    re9_pose_write_status()
end

local function re9_pose_run_physics_probe()
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then
        re9_pose_logger.physics_probe_status = "freecam disabled"
        re9_pose_logger.physics_probe_error = "Enable FreeCam before physics probe"
        re9_pose_write_status()
        return
    end
    local x, y, z, yaw_value, pitch_value = re9_pose_get_pose()
    local origin = re9_pose_vec3(x, y, z)
    local ray_len = 0.35
    local clip_distance = tonumber(re9_pose_logger.physics_clip_distance) or 0.03
    local near_distance = tonumber(re9_pose_logger.physics_near_distance) or 0.12
    local sphere_radius = tonumber(re9_pose_logger.physics_sphere_radius) or 0.08
    local filter, filter_layer, filter_mask_bit, filter_mask_bits = re9_pose_current_filter()
    local ok_sphere, sphere_msg, sphere_contacts = re9_pose_run_closest_sphere(origin, sphere_radius, filter, filter_mask_bits)
    local ok_penetration, penetration_msg, sphere_penetrating = re9_pose_run_resolve_penetration(origin, sphere_radius, filter)
    local sphere_sweep = {0.01, 0.03, 0.06, sphere_radius}
    local sphere_sweep_parts = {}
    local sphere_sweep_ok = 0
    local sphere_sweep_hits = 0
    for _, radius in ipairs(sphere_sweep) do
        local ok_p, msg_p, hit_p = re9_pose_run_resolve_penetration(origin, radius, filter)
        if ok_p then
            sphere_sweep_ok = sphere_sweep_ok + 1
            if hit_p == true then sphere_sweep_hits = sphere_sweep_hits + 1 end
            table.insert(sphere_sweep_parts, string.format("%.3f:%s", radius, tostring(hit_p)))
        else
            table.insert(sphere_sweep_parts, string.format("%.3f:err", radius))
        end
    end
    local inside_contacts = 0
    local min_probe_distance = nil
    local near_zero_dirs = 0
    local close_dirs = 0
    local rays = 0
    local errors = {}
    local hit_dirs = 0
    local detail_parts = {}
    local dirs = re9_pose_probe_dirs()
    for _, item in ipairs(dirs) do
        local label = item[1]
        local target = re9_pose_vec3(x + item[2] * ray_len, y + item[3] * ray_len, z + item[4] * ray_len)
        local ok_i, msg_i, count_i, dist_i = re9_pose_run_single_cast_ray(origin, target, true, filter)
        rays = rays + 1
        if ok_i then
            local c = tonumber(count_i) or 0
            inside_contacts = inside_contacts + c
            if c > 0 then hit_dirs = hit_dirs + 1 end
        else
            table.insert(errors, label .. ":inside:" .. tostring(msg_i))
        end
        if dist_i ~= nil and (min_probe_distance == nil or dist_i < min_probe_distance) then min_probe_distance = dist_i end
        if dist_i ~= nil and dist_i <= clip_distance then near_zero_dirs = near_zero_dirs + 1 end
        if dist_i ~= nil and dist_i < near_distance then close_dirs = close_dirs + 1 end
    end
    local fx, fy, fz = re9_pose_forward_dir(yaw_value, pitch_value)
    local ok_f, msg_f, count_f, dist_f = re9_pose_run_single_cast_ray(origin, re9_pose_vec3(x + fx * ray_len, y + fy * ray_len, z + fz * ray_len), true, filter)
    rays = rays + 1
    if ok_f then
        local c = tonumber(count_f) or 0
        inside_contacts = inside_contacts + c
        if c > 0 then hit_dirs = hit_dirs + 1 end
        if dist_f ~= nil and (min_probe_distance == nil or dist_f < min_probe_distance) then min_probe_distance = dist_f end
        if dist_f ~= nil and dist_f <= clip_distance then near_zero_dirs = near_zero_dirs + 1 end
        if dist_f ~= nil and dist_f < near_distance then close_dirs = close_dirs + 1 end
    else
        table.insert(errors, "forward:inside:" .. tostring(msg_f))
    end
    table.insert(detail_parts, "filter_layer=" .. tostring(filter_layer) .. " mask_bit=" .. tostring(filter_mask_bit) .. " mask=" .. tostring(filter_mask_bits))
    table.insert(detail_parts, "sphere_r=" .. string.format("%.3f", sphere_radius) .. " sphere_penetrating=" .. tostring(sphere_penetrating) .. " penetration_ok=" .. tostring(ok_penetration) .. " sphere_contacts=" .. tostring(sphere_contacts or "?") .. " closest_ok=" .. tostring(ok_sphere))
    table.insert(detail_parts, "sphere_sweep=" .. table.concat(sphere_sweep_parts, ","))
    table.insert(detail_parts, "ray_hit_dirs=" .. tostring(hit_dirs) .. "/" .. tostring(rays) .. " ray_contacts=" .. tostring(inside_contacts) .. " close_dirs=" .. tostring(close_dirs) .. " clip_dirs=" .. tostring(near_zero_dirs))
    table.insert(detail_parts, "min_d=" .. tostring(min_probe_distance ~= nil and string.format("%.4f", min_probe_distance) or "?") .. " forward_i=" .. tostring(count_f or "?") .. " forward_d=" .. tostring(dist_f ~= nil and string.format("%.4f", dist_f) or "?"))
    if not ok_sphere then table.insert(errors, "closestSphere:" .. tostring(sphere_msg)) end
    if not ok_penetration then table.insert(errors, "resolvePenetration:" .. tostring(penetration_msg)) end
    re9_pose_logger.physics_probe_contacts = hit_dirs
    re9_pose_logger.physics_probe_rays = rays
    re9_pose_logger.physics_probe_details = table.concat(detail_parts, "; ")
    local ray_saturated = rays > 0 and hit_dirs >= rays and near_zero_dirs == 0
    local sphere_saturated = sphere_sweep_ok > 0 and sphere_sweep_hits >= sphere_sweep_ok and ray_saturated
    local saturation_suspect = sphere_saturated and re9_pose_logger.physics_saturation_invalid == true
    local ray_suspect = near_zero_dirs >= 2 or (min_probe_distance ~= nil and min_probe_distance <= clip_distance)
    local sphere_suspect = ok_penetration and sphere_penetrating == true and not sphere_saturated
    local suspect = saturation_suspect or sphere_suspect or ray_suspect
    re9_pose_logger.physics_probe_pose_valid = not suspect
    if #errors > 0 and (not ok_sphere or not ok_penetration) then
        re9_pose_logger.physics_probe_status = "error"
        re9_pose_logger.physics_probe_error = table.concat(errors, " | ")
    elseif sphere_saturated then
        re9_pose_logger.physics_probe_status = saturation_suspect and "probe_saturated_invalid" or "probe_saturated"
        re9_pose_logger.physics_probe_error = "physics signals are saturated; sphere_sweep=" .. table.concat(sphere_sweep_parts, ",") .. " hit_dirs=" .. tostring(hit_dirs) .. "/" .. tostring(rays) .. " min_distance=" .. tostring(min_probe_distance or "?")
    elseif suspect then
        re9_pose_logger.physics_probe_status = sphere_suspect and "sphere_penetration" or "suspect_clip"
        re9_pose_logger.physics_probe_error = "sphere_penetrating=" .. tostring(sphere_penetrating) .. " sphere_contacts=" .. tostring(sphere_contacts or "?") .. " near_zero_dirs=" .. tostring(near_zero_dirs) .. " min_distance=" .. tostring(min_probe_distance or "?") .. " clip_distance=" .. tostring(clip_distance)
    elseif min_probe_distance ~= nil and min_probe_distance < near_distance then
        re9_pose_logger.physics_probe_status = "near_surface"
        re9_pose_logger.physics_probe_error = "min_distance=" .. tostring(min_probe_distance) .. " near_distance=" .. tostring(near_distance) .. " sphere_contacts=" .. tostring(sphere_contacts or "?")
    else
        re9_pose_logger.physics_probe_status = "api_ok_clear"
        re9_pose_logger.physics_probe_error = ""
    end
    re9_pose_write_status()
end

local function re9_pose_scan_physics_filter_bits()
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then
        re9_pose_logger.physics_probe_status = "freecam disabled"
        re9_pose_logger.physics_probe_error = "Enable FreeCam before scanning physics filters"
        re9_pose_write_status()
        return
    end
    local x, y, z, yaw_value, pitch_value = re9_pose_get_pose()
    local origin = re9_pose_vec3(x, y, z)
    local sphere_radius = tonumber(re9_pose_logger.physics_sphere_radius) or 0.08
    local layer = math.floor(tonumber(re9_pose_logger.physics_filter_layer) or 0)
    if layer < 0 then layer = 0 elseif layer > 31 then layer = 31 end
    local fx, fy, fz = re9_pose_forward_dir(yaw_value, pitch_value)
    local forward_target = re9_pose_vec3(x + fx * 0.35, y + fy * 0.35, z + fz * 0.35)
    local parts = {}
    local active = 0
    for bit = 0, 31 do
        local mask = 2 ^ bit
        local filter = re9_pose_create_filter_info(layer, mask)
        local ok_p, msg_p, penetrating = re9_pose_run_resolve_penetration(origin, sphere_radius, filter)
        local ok_c, msg_c, closest_contacts = re9_pose_run_closest_sphere(origin, sphere_radius, filter, mask)
        local ok_r, msg_r, ray_contacts, ray_dist = re9_pose_run_single_cast_ray(origin, forward_target, true, filter)
        local c = tonumber(closest_contacts) or 0
        local r = tonumber(ray_contacts) or 0
        if penetrating == true or c > 0 or r > 0 then
            active = active + 1
            table.insert(parts, "b" .. tostring(bit) .. ":p" .. tostring(penetrating == true) .. ":c" .. tostring(c) .. ":r" .. tostring(r) .. ":d" .. tostring(ray_dist ~= nil and string.format("%.3f", ray_dist) or "?"))
        elseif not ok_p or not ok_c or not ok_r then
            table.insert(parts, "b" .. tostring(bit) .. ":err")
        end
    end
    re9_pose_logger.physics_probe_status = "filter_scan"
    re9_pose_logger.physics_probe_pose_valid = true
    re9_pose_logger.physics_probe_contacts = active
    re9_pose_logger.physics_probe_rays = 32
    re9_pose_logger.physics_probe_details = "filter_layer=" .. tostring(layer) .. " active_bits=" .. tostring(active) .. "; " .. table.concat(parts, "; ")
    re9_pose_logger.physics_probe_error = "Compare this at a normal point and a clipped point; choose a mask bit that changes."
    re9_pose_write_status()
end

local function re9_pose_start(session_id, pose_log_file, interval_sec)
    if io == nil or io.open == nil then
        re9_pose_logger.last_error = "io.open unavailable in this REFramework Lua environment"
        re9_pose_write_status()
        return
    end
    if re9_pose_logger.file_handle ~= nil then pcall(function() re9_pose_logger.file_handle:close() end) end
    re9_pose_logger.session_id = session_id or os.date("%Y%m%d_%H%M%S")
    re9_pose_logger.pose_log_file = re9_pose_csv_path(pose_log_file or re9_pose_logger.pose_log_file)
    re9_pose_logger.interval_sec = tonumber(interval_sec) or re9_pose_logger.interval_sec
    re9_pose_logger.rows_written = 0
    re9_pose_logger.session_start_clock = os.clock()
    re9_pose_logger.last_sample_clock = 0
    re9_pose_logger.last_error = ""
    local ok, result = pcall(function() return io.open(re9_pose_logger.pose_log_file, "w") end)
    if not ok or result == nil then
        re9_pose_logger.logging = false
        re9_pose_logger.last_error = "Could not open pose log file: " .. tostring(result)
        re9_pose_write_status()
        return
    end
    re9_pose_logger.file_handle = result
    re9_pose_logger.file_handle:write("session_id,timestamp_sec,x,y,z,yaw,yaw_norm_rad,yaw_norm_deg,pitch,fov,freecam_mode,user_has_rotated\n")
    re9_pose_logger.logging = true
    re9_pose_write_status()
end

local function re9_pose_stop()
    re9_pose_logger.logging = false
    re9_pose_logger.scan_pose_enabled = false
    re9_pose_logger.scan_segment_id = ""
    re9_pose_logger.trajectory_enabled = false
    re9_pose_logger.trajectory_id = ""
    re9_pose_logger.trajectory_keyframes = nil
    re9_pose_logger.trajectory_frame_count = 0
    if re9_pose_logger.file_handle ~= nil then
        pcall(function() re9_pose_logger.file_handle:flush(); re9_pose_logger.file_handle:close() end)
        re9_pose_logger.file_handle = nil
    end
    re9_pose_write_status()
end

local function re9_pose_set_scan_pose(control)
    if control == nil then return end
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then
        re9_pose_logger.last_error = "Enable FreeCam before running scan set_pose"
        re9_pose_write_status()
        return
    end
    re9_pose_logger.scan_pose_enabled = true
    re9_pose_logger.scan_segment_id = tostring(control.segment_id or "")
    re9_pose_logger.scan_x = tonumber(control.x) or re9_pose_logger.scan_x
    re9_pose_logger.scan_y = tonumber(control.y) or re9_pose_logger.scan_y
    re9_pose_logger.scan_z = tonumber(control.z) or re9_pose_logger.scan_z
    re9_pose_logger.scan_x_start = re9_pose_logger.scan_x
    re9_pose_logger.scan_y_start = re9_pose_logger.scan_y
    re9_pose_logger.scan_z_start = re9_pose_logger.scan_z
    re9_pose_logger.scan_x_end = tonumber(control.x_end) or re9_pose_logger.scan_x
    re9_pose_logger.scan_y_end = tonumber(control.y_end) or re9_pose_logger.scan_y
    re9_pose_logger.scan_z_end = tonumber(control.z_end) or re9_pose_logger.scan_z
    re9_pose_logger.scan_yaw = tonumber(control.yaw) or re9_pose_logger.scan_yaw
    re9_pose_logger.scan_yaw_start = re9_pose_logger.scan_yaw
    re9_pose_logger.scan_yaw_end = tonumber(control.yaw_end) or re9_pose_logger.scan_yaw
    re9_pose_logger.scan_pitch = tonumber(control.pitch) or re9_pose_logger.scan_pitch
    re9_pose_logger.scan_pitch_start = re9_pose_logger.scan_pitch
    re9_pose_logger.scan_pitch_end = tonumber(control.pitch_end) or re9_pose_logger.scan_pitch
    re9_pose_logger.scan_duration_sec = tonumber(control.duration_sec) or 0
    re9_pose_logger.scan_start_clock = os.clock()
    if control.fov ~= nil then re9_pose_logger.scan_fov = tonumber(control.fov) end
    re9_pose_logger.scan_fov_start = re9_pose_logger.scan_fov
    re9_pose_logger.scan_fov_end = tonumber(control.fov_end) or re9_pose_logger.scan_fov
    re9_pose_logger.last_error = ""
    re9_pose_write_status()
end

local function re9_pose_clear_scan_pose()
    re9_pose_logger.scan_pose_enabled = false
    re9_pose_logger.scan_segment_id = ""
    re9_pose_logger.trajectory_enabled = false
    re9_pose_logger.trajectory_id = ""
    re9_pose_logger.trajectory_keyframes = nil
    re9_pose_logger.trajectory_frame_count = 0
    re9_pose_write_status()
end

local function re9_pose_set_trajectory(control)
    if control == nil then return end
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then
        re9_pose_logger.last_error = "Enable FreeCam before running play_trajectory"
        re9_pose_write_status()
        return
    end
    local frames = control.keyframes
    if type(frames) ~= "table" or #frames < 2 then
        re9_pose_logger.last_error = "play_trajectory requires at least two keyframes and json.load_file support"
        re9_pose_write_status()
        return
    end
    table.sort(frames, function(a, b) return (tonumber(a.time_sec) or 0) < (tonumber(b.time_sec) or 0) end)
    for i, frame in ipairs(frames) do
        frame.time_sec = tonumber(frame.time_sec) or ((i - 1) * 0.2)
        frame.x = tonumber(frame.x) or 0
        frame.y = tonumber(frame.y) or 0
        frame.z = tonumber(frame.z) or 0
        frame.yaw = tonumber(frame.yaw) or 0
        frame.pitch = tonumber(frame.pitch) or 0
        if frame.fov ~= nil then frame.fov = tonumber(frame.fov) end
    end
    re9_pose_logger.scan_pose_enabled = true
    re9_pose_logger.scan_segment_id = tostring(control.trajectory_id or "trajectory")
    re9_pose_logger.trajectory_enabled = true
    re9_pose_logger.trajectory_id = tostring(control.trajectory_id or "trajectory")
    re9_pose_logger.trajectory_keyframes = frames
    re9_pose_logger.trajectory_start_clock = os.clock()
    re9_pose_logger.trajectory_duration_sec = tonumber(frames[#frames].time_sec) or 0
    re9_pose_logger.trajectory_frame_count = #frames
    re9_pose_logger.last_error = ""
    re9_pose_write_status()
end

local function re9_pose_apply_frame_pair(a, b, t)
    if a == nil then return end
    if b == nil then b = a end
    if t < 0 then t = 0 end
    if t > 1 then t = 1 end
    freecam_pos.x = (tonumber(a.x) or 0) + ((tonumber(b.x) or tonumber(a.x) or 0) - (tonumber(a.x) or 0)) * t
    freecam_pos.y = (tonumber(a.y) or 0) + ((tonumber(b.y) or tonumber(a.y) or 0) - (tonumber(a.y) or 0)) * t
    freecam_pos.z = (tonumber(a.z) or 0) + ((tonumber(b.z) or tonumber(a.z) or 0) - (tonumber(a.z) or 0)) * t
    freecam_yaw = (tonumber(a.yaw) or 0) + ((tonumber(b.yaw) or tonumber(a.yaw) or 0) - (tonumber(a.yaw) or 0)) * t
    freecam_pitch = (tonumber(a.pitch) or 0) + ((tonumber(b.pitch) or tonumber(a.pitch) or 0) - (tonumber(a.pitch) or 0)) * t
    if a.fov ~= nil and b.fov ~= nil then
        global_fov = (tonumber(a.fov) or 0) + ((tonumber(b.fov) or tonumber(a.fov) or 0) - (tonumber(a.fov) or 0)) * t
        use_custom_fov = true
    end
    user_has_rotated = true
    yaw_pitch_initialized = true
end

local function re9_pose_apply_trajectory_pose()
    if not re9_pose_logger.trajectory_enabled then return false end
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then return true end
    local frames = re9_pose_logger.trajectory_keyframes
    if type(frames) ~= "table" or #frames < 1 then return true end
    local elapsed = os.clock() - (tonumber(re9_pose_logger.trajectory_start_clock) or os.clock())
    if elapsed >= (tonumber(re9_pose_logger.trajectory_duration_sec) or 0) then
        re9_pose_apply_frame_pair(frames[#frames], frames[#frames], 1)
        re9_pose_logger.trajectory_enabled = false
        re9_pose_logger.scan_pose_enabled = false
        return true
    end
    local previous = frames[1]
    for i = 2, #frames do
        local current = frames[i]
        local a_time = tonumber(previous.time_sec) or 0
        local b_time = tonumber(current.time_sec) or a_time
        if elapsed <= b_time then
            local span = b_time - a_time
            local t = 1
            if span > 0 then t = (elapsed - a_time) / span end
            re9_pose_apply_frame_pair(previous, current, t)
            return true
        end
        previous = current
    end
    re9_pose_apply_frame_pair(frames[#frames], frames[#frames], 1)
    return true
end

local function re9_pose_apply_scan_pose()
    if not re9_pose_logger.scan_pose_enabled then return end
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then return end
    if re9_pose_apply_trajectory_pose() then return end
    local t = 1
    if re9_pose_logger.scan_duration_sec ~= nil and re9_pose_logger.scan_duration_sec > 0 then
        t = (os.clock() - re9_pose_logger.scan_start_clock) / re9_pose_logger.scan_duration_sec
        if t < 0 then t = 0 end
        if t > 1 then t = 1 end
    end
    freecam_pos.x = re9_pose_logger.scan_x_start + (re9_pose_logger.scan_x_end - re9_pose_logger.scan_x_start) * t
    freecam_pos.y = re9_pose_logger.scan_y_start + (re9_pose_logger.scan_y_end - re9_pose_logger.scan_y_start) * t
    freecam_pos.z = re9_pose_logger.scan_z_start + (re9_pose_logger.scan_z_end - re9_pose_logger.scan_z_start) * t
    local yaw_value = re9_pose_logger.scan_yaw
    yaw_value = re9_pose_logger.scan_yaw_start + (re9_pose_logger.scan_yaw_end - re9_pose_logger.scan_yaw_start) * t
    re9_pose_logger.scan_yaw = yaw_value
    freecam_yaw = yaw_value
    freecam_pitch = re9_pose_logger.scan_pitch_start + (re9_pose_logger.scan_pitch_end - re9_pose_logger.scan_pitch_start) * t
    if re9_pose_logger.scan_fov_start ~= nil and re9_pose_logger.scan_fov_end ~= nil then
        global_fov = re9_pose_logger.scan_fov_start + (re9_pose_logger.scan_fov_end - re9_pose_logger.scan_fov_start) * t
        use_custom_fov = true
    end
    user_has_rotated = true
    yaw_pitch_initialized = true
end

local function re9_pose_write_scan_camera()
    if not re9_pose_logger.scan_pose_enabled and not re9_pose_logger.trajectory_enabled then return end
    if not re9_pose_is_freecam_mode() or freecam_pos == nil then return end
    re9_pose_apply_scan_pose()
    if type(write_yawpitch_matrix) == "function" then
        pcall(function() write_yawpitch_matrix(freecam_pos.x, freecam_pos.y, freecam_pos.z, freecam_yaw, freecam_pitch) end)
    end
end

local function re9_pose_get_number(name, fallback)
    local value = _G[name]
    if type(value) == "number" then return value end
    return fallback or 0
end

re9_pose_get_pose = function()
    local pos = nil
    if type(freecam_pos) ~= "nil" then pos = freecam_pos end
    if pos == nil and type(camera_pos) ~= "nil" then pos = camera_pos end
    if pos == nil then return nil end
    local x = pos.x or pos[1] or 0
    local y = pos.y or pos[2] or 0
    local z = pos.z or pos[3] or 0
    local yaw_value = 0
    local pitch_value = 0
    local fov_value = 0
    if type(freecam_yaw) ~= "nil" then yaw_value = freecam_yaw elseif type(yaw) ~= "nil" then yaw_value = yaw else yaw_value = re9_pose_get_number("yaw", 0) end
    if type(freecam_pitch) ~= "nil" then pitch_value = freecam_pitch elseif type(pitch) ~= "nil" then pitch_value = pitch else pitch_value = re9_pose_get_number("pitch", 0) end
    if type(global_fov) ~= "nil" then fov_value = global_fov elseif type(fov) ~= "nil" then fov_value = fov else fov_value = re9_pose_get_number("fov", 0) end
    return x, y, z, yaw_value, pitch_value, fov_value
end

function re9_pose_is_freecam_mode()
    if type(freecam_mode) ~= "nil" then return freecam_mode == true end
    if type(is_freecam) ~= "nil" then return is_freecam == true end
    if type(enabled) ~= "nil" then return enabled == true end
    return false
end

local function re9_pose_log_sample()
    if not re9_pose_logger.enabled or not re9_pose_logger.logging then return end
    if not re9_pose_is_freecam_mode() then return end
    local x, y, z, yaw_value, pitch_value, fov_value = re9_pose_get_pose()
    if x == nil then return end
    local now = os.clock()
    if re9_pose_logger.last_sample_clock ~= 0 and (now - re9_pose_logger.last_sample_clock) < re9_pose_logger.interval_sec then return end
    re9_pose_logger.last_sample_clock = now
    local timestamp_sec = now - re9_pose_logger.session_start_clock
    local rotated = false
    if type(user_has_rotated) ~= "nil" then rotated = user_has_rotated == true end
    local yaw_norm_rad = yaw_value % (math.pi * 2)
    if yaw_norm_rad < 0 then yaw_norm_rad = yaw_norm_rad + (math.pi * 2) end
    local yaw_norm_deg = math.deg(yaw_norm_rad)
    local ok, err = pcall(function()
        re9_pose_logger.file_handle:write(string.format("%s,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.6f,%.9f,%.9f,%s,%s\n",
            re9_pose_logger.session_id, timestamp_sec, x, y, z, yaw_value, yaw_norm_rad, yaw_norm_deg, pitch_value, fov_value,
            tostring(re9_pose_is_freecam_mode()), tostring(rotated)))
        re9_pose_logger.rows_written = re9_pose_logger.rows_written + 1
        if re9_pose_logger.rows_written % 30 == 0 then re9_pose_logger.file_handle:flush(); re9_pose_write_status() end
    end)
    if not ok then re9_pose_logger.last_error = tostring(err); re9_pose_write_status() end
end

local function re9_pose_write_new_scene_json()
    local csv_path = re9_pose_data_path(re9_pose_logger.new_scene_points_file)
    local json_path = re9_pose_data_path(re9_pose_logger.new_scene_points_json_file)
    local f = io.open(csv_path, "r")
    if f == nil then return end
    local rows = {}
    local header = f:read("*l")
    local line = f:read("*l")
    while line ~= nil do
        local index, x, y, z, yaw, pitch, fov = line:match('([^,]+),[^,]+,([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+)')
        if index ~= nil then
            table.insert(rows, string.format('{"index":%d,"x":%.9f,"y":%.9f,"z":%.9f,"yaw":%.9f,"pitch":%.9f,"fov":%.9f}',
                tonumber(index) or 0, tonumber(x) or 0, tonumber(y) or 0, tonumber(z) or 0, tonumber(yaw) or 0, tonumber(pitch) or 0, tonumber(fov) or 0))
        end
        line = f:read("*l")
    end
    f:close()
    local out = io.open(json_path, "w")
    if out ~= nil then
        out:write('{"scene":"new_scene","points":[' .. table.concat(rows, ",") .. ']}')
        out:close()
    end
end

local function re9_pose_capture_new_scene_point()
    if not re9_pose_is_freecam_mode() then
        re9_pose_logger.last_error = "Enable FreeCam before capturing a new scene point"
        re9_pose_write_status()
        return
    end
    local x, y, z, yaw_value, pitch_value, fov_value = re9_pose_get_pose()
    if x == nil then
        re9_pose_logger.last_error = "No FreeCam pose is available to capture"
        re9_pose_write_status()
        return
    end
    local count = (tonumber(re9_pose_logger.new_scene_point_count) or 0) + 1
    local csv_path = re9_pose_data_path(re9_pose_logger.new_scene_points_file)
    local exists = false
    local check = io.open(csv_path, "r")
    if check ~= nil then exists = true; check:close() end
    local f = io.open(csv_path, "a")
    if f == nil then
        re9_pose_logger.last_error = "Could not open new scene points file"
        re9_pose_write_status()
        return
    end
    if not exists then f:write("index,timestamp_sec,x,y,z,yaw,pitch,fov\n") end
    f:write(string.format("%d,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f\n", count, os.clock(), x, y, z, yaw_value, pitch_value, fov_value))
    f:close()
    re9_pose_logger.new_scene_point_count = count
    re9_pose_logger.new_scene_last_point = string.format("%02d x=%.2f y=%.2f z=%.2f", count, x, y, z)
    re9_pose_logger.last_error = ""
    pcall(re9_pose_write_new_scene_json)
    re9_pose_write_status()
end

local function re9_pose_reset_new_scene_points()
    local csv_path = re9_pose_data_path(re9_pose_logger.new_scene_points_file)
    local json_path = re9_pose_data_path(re9_pose_logger.new_scene_points_json_file)
    local f = io.open(csv_path, "w")
    if f ~= nil then f:write("index,timestamp_sec,x,y,z,yaw,pitch,fov\n"); f:close() end
    local out = io.open(json_path, "w")
    if out ~= nil then out:write('{"scene":"new_scene","points":[]}'); out:close() end
    re9_pose_logger.new_scene_point_count = 0
    re9_pose_logger.new_scene_last_point = ""
    re9_pose_logger.last_error = ""
    re9_pose_write_status()
end

local function re9_pose_poll_control()
    local now = os.clock()
    if (now - re9_pose_logger.last_control_clock) < 0.25 then return end
    re9_pose_logger.last_control_clock = now
    local control = re9_pose_read_control()
    if control == nil or control.command == nil then return end
    local command_id = tostring(control.command_id or control.command or "")
    if command_id ~= "" and command_id == re9_pose_logger.last_command_id then return end
    re9_pose_logger.last_command_id = command_id
    if control.command == "start" and control.session_id ~= re9_pose_logger.session_id then
        re9_pose_start(control.session_id, control.pose_log_file, control.interval_sec)
    elseif control.command == "stop" and control.session_id == re9_pose_logger.session_id then
        re9_pose_stop()
    elseif control.command == "set_pose" then
        re9_pose_set_scan_pose(control)
    elseif control.command == "play_trajectory" then
        re9_pose_set_trajectory(control)
    elseif control.command == "clear_pose" then
        re9_pose_clear_scan_pose()
    elseif control.command == "physics_probe" then
        re9_pose_run_physics_probe()
    end
end

re.on_pre_application_entry("LateUpdateBehavior", function()
    pcall(re9_pose_apply_scan_pose)
end)

re.on_pre_application_entry("LockScene", function()
    pcall(re9_pose_write_scan_camera)
end)

re.on_frame(function()
    pcall(re9_pose_poll_control)
    pcall(re9_pose_apply_scan_pose)
    pcall(re9_pose_log_sample)
end)

re.on_draw_ui(function()
    if imgui.tree_node("RE9 Aesthetic Pose Logger") then
        changed, re9_pose_logger.enabled = imgui.checkbox("Pose Logging Enabled", re9_pose_logger.enabled)
        changed, re9_pose_logger.interval_sec = imgui.slider_float("Logging Interval", re9_pose_logger.interval_sec, 0.005, 1.0)
        if imgui.button("Start Pose Log") then re9_pose_start(os.date("%Y%m%d_%H%M%S"), re9_pose_logger.pose_log_file, re9_pose_logger.interval_sec) end
        imgui.same_line()
        if imgui.button("Stop Pose Log") then re9_pose_stop() end
        imgui.text("Logger status: " .. tostring(re9_pose_logger.logging))
        imgui.text("Session id: " .. tostring(re9_pose_logger.session_id))
        imgui.text("Rows written: " .. tostring(re9_pose_logger.rows_written))
        imgui.text("Pose log file: " .. tostring(re9_pose_logger.pose_log_file))
        imgui.text("New scene points: " .. tostring(re9_pose_logger.new_scene_point_count) .. "/8")
        if imgui.button("Capture New Scene Point") then re9_pose_capture_new_scene_point() end
        imgui.same_line()
        if imgui.button("Reset New Scene Points") then re9_pose_reset_new_scene_points() end
        if re9_pose_logger.new_scene_last_point ~= "" then imgui.text("Last new scene point: " .. tostring(re9_pose_logger.new_scene_last_point)) end
        imgui.text("New scene file: " .. tostring(re9_pose_logger.new_scene_points_file))
        imgui.text("Scan pose enabled: " .. tostring(re9_pose_logger.scan_pose_enabled))
        imgui.text("Scan segment id: " .. tostring(re9_pose_logger.scan_segment_id))
        changed, re9_pose_logger.physics_clip_distance = imgui.slider_float("Physics Clip Distance", re9_pose_logger.physics_clip_distance, 0.005, 0.2)
        changed, re9_pose_logger.physics_near_distance = imgui.slider_float("Physics Near Distance", re9_pose_logger.physics_near_distance, 0.02, 0.5)
        changed, re9_pose_logger.physics_sphere_radius = imgui.slider_float("Physics Sphere Radius", re9_pose_logger.physics_sphere_radius, 0.01, 0.3)
        changed, re9_pose_logger.physics_filter_layer = imgui.slider_float("Physics Filter Layer", re9_pose_logger.physics_filter_layer, 0, 31)
        changed, re9_pose_logger.physics_filter_mask_bit = imgui.slider_float("Physics Mask Bit", re9_pose_logger.physics_filter_mask_bit, 0, 31)
        changed, re9_pose_logger.physics_saturation_invalid = imgui.checkbox("Treat Saturated Probe As Invalid", re9_pose_logger.physics_saturation_invalid)
        if imgui.button("Test Physics Probe") then re9_pose_run_physics_probe() end
        imgui.same_line()
        if imgui.button("Scan Physics Filter Bits") then re9_pose_scan_physics_filter_bits() end
        if imgui.button("Probe Camera Collision") then re9_pose_probe_camera_collision_system() end
        imgui.text("Physics probe: " .. tostring(re9_pose_logger.physics_probe_status) .. " valid=" .. tostring(re9_pose_logger.physics_probe_pose_valid) .. " hit_dirs=" .. tostring(re9_pose_logger.physics_probe_contacts) .. "/" .. tostring(re9_pose_logger.physics_probe_rays))
        if re9_pose_logger.physics_probe_details ~= "" then imgui.text("Physics details: " .. tostring(re9_pose_logger.physics_probe_details)) end
        if re9_pose_logger.physics_probe_error ~= "" then imgui.text("Physics error: " .. tostring(re9_pose_logger.physics_probe_error)) end
        if re9_pose_logger.last_error ~= "" then imgui.text("Last error: " .. tostring(re9_pose_logger.last_error)) end
        imgui.tree_pop()
    end
end)
-- END RE9_AESTHETIC_POSE_LOGGER
